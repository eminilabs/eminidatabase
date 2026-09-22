# Déploiement sur VPS partagé (srv1963488)

Ce runbook déploie eminidatabase aux côtés d'eminiAI et eminihub sur le même
VPS, complètement isolé (son propre réseau Docker, ses propres volumes, ses
propres ports) et proxié par l'Apache déjà en place pour les autres projets.

Domaines : `database.eminilabs.org` (frontend) et `apidatabase.eminilabs.org`
(backend), sous-domaines temporaires d'eminilabs.org en attendant l'achat du
nom de domaine propre à eminidatabase.

## Topologie

- **Control Plane** (backend + worker + scheduler + frontend + leur propre
  Postgres) tourne dans Docker, réseau interne `eminidatabase_internal`
  (sous-réseau fixe `172.20.0.0/24`, passerelle `172.20.0.1`).
- **Data Plane Agent** tourne **nativement sur l'hôte** (pas dans Docker) :
  il a besoin de voir les vraies ressources de la machine (`psutil`) et, en
  production réelle, d'utiliser `pg_dump`/`pg_restore` en binaires locaux —
  exposer le socket Docker à un conteneur pour faire du `docker exec` depuis
  l'intérieur aurait été un vrai risque sur une machine qui héberge d'autres
  projets. Sa Postgres (`node-postgres`) tourne quand même dans Docker (comme
  en dev), l'agent la pilote juste en SQL (`app/postgres_admin.py`, jamais de
  shell) via un DSN admin, et route `pg_dump`/`pg_restore` par `docker exec`.
- Le backend (conteneur) a besoin de joindre directement l'agent (mTLS) *et*
  `node-postgres` (SQL Editor, `app/services/sql_editor.py`) — les deux sont
  donc publiés sur l'IP fixe de la passerelle (`172.20.0.1`), jamais sur
  `0.0.0.0` : ufw bloque tout le reste par défaut (`default deny incoming`),
  ce n'est joignable que depuis l'intérieur du réseau Docker ou du host.

## 1. Prérequis

- DNS : `database.eminilabs.org` et `apidatabase.eminilabs.org` → A record
  `185.199.52.103`, proxied (Cloudflare), comme `hub.eminilabs.org`.
- Accès SSH `deploy@185.199.52.103` (sudo passwordless déjà en place).

## 2. Cloner le repo

```bash
sudo mkdir -p /opt/projects/eminidatabase
sudo chown deploy:deploy /opt/projects/eminidatabase
cd /opt/projects
git clone git@github.com:eminilabs/eminidatabase.git eminidatabase
cd eminidatabase
```

(Nécessite que la clé de déploiement GitHub du VPS ait accès en lecture au
repo `eminilabs/eminidatabase` — deploy key à ajouter côté GitHub si pas déjà
fait pour ce repo précis.)

## 3. Secrets

```bash
cp .env.production.example .env
cp backend/.env.production.example backend/.env.production
cp agent/.env.production.example agent/.env.production
```

Générer et remplacer chaque `replace-with-...` :
- Mots de passe Postgres/MinIO : `openssl rand -base64 32`
- `JWT_SECRET_KEY` : `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
- `SECRET_ENCRYPTION_KEY` / `BACKUP_ENCRYPTION_KEY` (Fernet, **deux clés
  différentes**) : `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

`backend/.env.production`'s `DATABASE_URL` et `agent/.env.production`'s
`POSTGRES_ADMIN_DSN`/`S3_ACCESS_KEY`/`S3_SECRET_KEY` doivent reprendre
exactement les mots de passe mis dans `.env` (racine).

## 4. Build + lancer le Control Plane

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps   # tout doit finir "healthy"
```

`migrate` tourne une fois et s'arrête (normal, `service_completed_successfully`).

ufw bloque par défaut tout ce qui n'a pas de règle explicite — y compris le
trafic venant du **pont Docker lui-même** vers un port publié sur l'hôte.
Sans ça, le backend ne peut joindre ni l'agent (mTLS, étape 8) ni
`node-postgres` (SQL Editor), et les créations de base restent bloquées en
retry avec `Agent call to ... failed` :

```bash
sudo ufw allow from 172.20.0.0/24 to any port 9443 proto tcp comment 'eminidatabase agent mTLS (internal only)'
sudo ufw allow from 172.20.0.0/24 to any port 5544 proto tcp comment 'eminidatabase node-postgres (internal only)'
```

## 5. Apache + certbot

```bash
sudo cp deploy/apache/database.eminilabs.org.conf /etc/apache2/sites-available/
sudo cp deploy/apache/apidatabase.eminilabs.org.conf /etc/apache2/sites-available/
sudo a2ensite database.eminilabs.org apidatabase.eminilabs.org
sudo systemctl reload apache2
sudo certbot --apache -d database.eminilabs.org -d apidatabase.eminilabs.org
```

Certbot réécrit les deux fichiers pour ajouter le bloc SSL + la redirection
80→443 (même pattern que les vhosts existants).

## 6. Compte platform-admin + premier utilisateur

```bash
# Un compte normal d'abord (POST /api/v1/auth/register), puis le promouvoir
# platform-admin directement en base (pas d'endpoint API pour ça, cf.
# app/models/user.py — is_platform_admin):
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U eminidatabase_owner -d eminidatabase \
  -c "UPDATE users SET is_platform_admin = true WHERE email = 'admin@eminilabs.org';"
```

## 7. Créer une région + un token d'enregistrement de node

Avec le token JWT du compte platform-admin (`POST /api/v1/auth/login`) :

```bash
curl -X POST https://apidatabase.eminilabs.org/api/v1/regions \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"code": "eu-west", "name": "Europe West"}'

curl -X POST https://apidatabase.eminilabs.org/api/v1/nodes/registration-tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"region_code": "eu-west"}'
# -> copier le token retourné dans agent/.env.production (BOOTSTRAP_TOKEN)
```

## 8. Agent natif (systemd)

L'hôte (Ubuntu 26.04 "resolute") n'a que Python 3.14 en natif, trop récent
pour les dépendances de l'agent (pydantic-core/asyncpg n'ont pas encore de
wheels compatibles, et PyO3 refuse même de compiler dessus). Un `python -m
venv` classique casse aussi : ses symlinks pointent vers l'interpréteur du
conteneur, qui disparaît avec lui. Solution : installer les dépendances dans
un conteneur `python:3.12-slim` puis copier tout `/usr/local` (interpréteur +
paquets, en vrais fichiers, pas des symlinks) vers l'hôte — un "venv" portable
qui ne dépend plus du conteneur.

```bash
cd /opt/projects/eminidatabase/agent
mkdir -p pyroot
docker run --rm -v "$(pwd):/agent" -w /agent python:3.12-slim bash -c '
  apt-get update -qq && apt-get install -y -qq --no-install-recommends gcc libpq-dev
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  cp -a /usr/local/. /agent/pyroot/
'
sudo chown -R deploy:deploy pyroot

# BOOTSTRAP_TOKEN doit être rempli dans agent/.env.production (étape 7)
set -a; source .env.production; set +a
pyroot/bin/python3.12 bootstrap.py
# -> génère state/node.key, node.crt, ca.crt

# Vider BOOTSTRAP_TOKEN dans .env.production (jeton à usage unique, déjà consommé)

sudo cp /opt/projects/eminidatabase/deploy/systemd/eminidatabase-agent.service \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eminidatabase-agent
sudo systemctl status eminidatabase-agent   # doit heartbeat toutes les 20s
```

Mise à jour ultérieure des dépendances de l'agent : relancer le bloc `docker
run` ci-dessus (il écrase `pyroot/` proprement), puis
`sudo systemctl restart eminidatabase-agent`.

## 9. Capacité réelle du node (VPS partagé — ne pas laisser l'auto-détection)

`psutil` rapporte les specs **totales de la VM** (4 vCPU / 15 Go / tout le
disque), ce qui surcommettrait la capacité alors qu'eminiAI et eminihub
tournent déjà dessus. Après l'enregistrement (étape 8), corriger
manuellement en base à une fraction sûre :

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U eminidatabase_owner -d eminidatabase \
  -c "UPDATE nodes SET cpu_total = 2, ram_total_mb = 4096, storage_total_gb = 30 WHERE hostname = 'vps-srv1963488-a';"
```

Ajuster ces chiffres à la hausse plus tard si la charge du VPS le permet
(`free -h`, `docker stats`).

## 10. Vérification

- `https://database.eminilabs.org` → page de login.
- `https://apidatabase.eminilabs.org/docs` → Swagger UI.
- Créer un compte, une organisation, un projet, une base → doit passer
  `creating` → `running` (le worker + l'agent font le vrai travail).

## Mises à jour

```bash
cd /opt/projects/eminidatabase
git pull
docker compose -f docker-compose.prod.yml up -d --build
# Si agent/ a changé :
cd agent && .venv/bin/pip install -r requirements.txt
sudo systemctl restart eminidatabase-agent
```
