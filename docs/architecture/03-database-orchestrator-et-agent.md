# 03 — Database Orchestrator & Data Plane Agent

## 3.1 Database Orchestrator

Service du Control Plane, séparé logiquement de l'API HTTP synchrone (il consomme une
queue de jobs). Responsable du cycle de vie complet d'une base.

### Responsabilités

| Domaine | Fonctions |
|---|---|
| Provisioning | placement (choix node/cluster/région), création, credentials, permissions, pooling, backup, monitoring |
| Lifecycle | start, stop, restart, suspend, resume, delete, recreate, migrate |
| Resources | allocation CPU/RAM/storage, limites de connexions, replicas |
| Reliability | health checks, détection de panne, failover, réplication |
| Maintenance | upgrades PostgreSQL, extensions, configuration |

### Algorithme de placement

```mermaid
flowchart TD
    R[Requête de création de base] --> P1{Permissions OK?}
    P1 -- non --> ERR1[403 Forbidden + audit]
    P1 -- oui --> P2{Quota du plan OK?}
    P2 -- non --> ERR2[402/429 Quota exceeded]
    P2 -- oui --> P3[Résoudre région demandée/par défaut]
    P3 --> P4[Lister nodes actifs de la région]
    P4 --> P5{Filtrer nodes compatibles\nisolation, version PG, capacité}
    P5 --> P6[Scorer les nodes\nCPU libre, RAM libre, IOPS,\nnb bases déjà présentes, charge]
    P6 --> P7{Un node dépasse le seuil\nde capacité disponible?}
    P7 -- non --> ERR3[Créer un job\n'provision_new_node'\nou renvoyer capacité insuffisante]
    P7 -- oui --> P8[Sélectionner le meilleur node]
    P8 --> P9[Créer le Job 'create_database'\navec idempotency_key]
    P9 --> Q[Enqueue vers le Worker]
```

Le scoring (§7 du cahier des charges) est un calcul simple et explicite au démarrage
(ex : `score = w1*cpu_libre + w2*ram_libre + w3*(1 - nb_bases/max_bases) - w4*charge`),
pas un mécanisme "boîte noire". Les poids sont configurables, pas codés en dur.

### Jobs et idempotence

Chaque opération longue est un enregistrement dans `JOBS` (cf. [02](02-modele-donnees.md))
avec :
- un `idempotency_key` dérivé de la requête cliente (évite la double création si le
  client retente une requête réseau en timeout) ;
- un nombre de tentatives borné avec backoff exponentiel ;
- un état terminal explicite (`succeeded`/`failed`), jamais de silence.

```mermaid
sequenceDiagram
    participant C as Client
    participant API as Control Plane API
    participant Q as Queue (Redis/Arq)
    participant W as Worker (Orchestrator)
    participant AG as Data Plane Agent
    participant PG as PostgreSQL

    C->>API: POST /projects/{id}/databases
    API->>API: auth, RBAC, quota
    API->>Q: enqueue job(create_database, idempotency_key)
    API-->>C: 202 Accepted {job_id, database_id, status: CREATING}
    Q->>W: dequeue job
    W->>W: sélection du node (placement)
    W->>AG: POST /provision (mTLS)
    AG->>PG: CREATE DATABASE / CREATE ROLE (paramétré, jamais de SQL concaténé)
    PG-->>AG: OK
    AG->>AG: configure PgBouncer, monitoring, backup policy
    AG-->>W: {status: running, endpoint, resource_usage}
    W->>API: update DATABASES.status = RUNNING (via DB directe ou event)
    W->>API: enregistre DATABASE_EVENTS + AUDIT_LOGS
    C->>API: GET /databases/{id} (polling ou webhook)
    API-->>C: {status: RUNNING, connection: {...}}
```

Le client interagit uniquement en HTTP asynchrone (202 + polling, ou webhook) —
jamais de requête HTTP bloquante de 30 secondes pendant qu'un `CREATE DATABASE` tourne
quelque part (Règle 11).

## 3.2 Data Plane Agent

Processus tournant sur chaque node, seul autorisé à exécuter des opérations locales.

### Surface exposée au Control Plane

```
POST   /v1/provision/database      -- créer une base + rôle + credentials
DELETE /v1/database/{name}         -- supprimer une base
POST   /v1/database/{name}/suspend
POST   /v1/database/{name}/resume
POST   /v1/database/{name}/resize  -- ajuster limites de connexions/ressources cgroups
GET    /v1/resources                -- CPU/RAM/disque disponibles
GET    /v1/health                   -- statut PostgreSQL, Redis, PgBouncer
POST   /v1/backup/run
POST   /v1/backup/verify
POST   /v1/restore
GET    /v1/metrics                  -- exposé aussi en scrape Prometheus direct
```

### Sécurité de la communication Control Plane ↔ Agent

- mTLS obligatoire (certificats émis par une CA interne à la plateforme, provisionnés
  au moment de l'enregistrement du node).
- Chaque agent a une identité unique (`node_id`) liée à son certificat — pas de secret
  partagé unique pour tous les nodes.
- L'agent n'accepte des commandes que depuis le Control Plane (allowlist réseau +
  vérification du certificat client), jamais depuis Internet public.
- Toute commande reçue est journalisée localement et remontée en audit log côté
  Control Plane.

### Construction sécurisée des commandes SQL

Rappel du cahier des charges (§10, étape 11) : **jamais de SQL construit par
concaténation de chaîne à partir d'une entrée utilisateur**. L'agent :
- valide le nom de la base/du rôle contre une regex stricte (`^[a-z][a-z0-9_]{2,62}$`)
  avant toute opération, côté API **et** côté agent (défense en profondeur) ;
- utilise des identifiants PostgreSQL passés via `psycopg`/`asyncpg` avec
  `sql.Identifier` (jamais de f-string dans une requête DDL) ;
- génère les mots de passe côté agent avec un générateur cryptographiquement sûr
  (`secrets.token_urlsafe`), jamais fournis par le client.

### Enregistrement d'un node (bootstrap)

```mermaid
sequenceDiagram
    participant Admin as Opérateur plateforme
    participant CP as Control Plane
    participant Node as Nouveau VPS
    Admin->>Node: installe l'agent (script/Ansible/cloud-init)
    Node->>CP: POST /v1/nodes/register {hostname, region, capacity, csr}
    CP->>CP: vérifie l'autorisation d'enregistrement (token one-shot)
    CP->>Node: signe le certificat, renvoie config (endpoints, node_id)
    Node->>CP: heartbeat périodique (toutes les 15-30s) via /v1/nodes/{id}/heartbeat
    CP->>CP: met à jour NODES.status, last_heartbeat_at
```

Un node sans heartbeat récent passe automatiquement `offline` côté Control Plane et
est exclu du placement — sans intervention manuelle.

## 3.3 Ce que l'Orchestrator ne fait jamais

- Il ne se connecte jamais directement à PostgreSQL sur un node (toujours via l'agent).
- Il ne suppose jamais qu'un node particulier est "le" node par défaut.
- Il ne marque jamais une opération comme terminée sans confirmation de l'agent.
- Il ne supprime jamais une ressource sans un job explicite et audité (pas de suppression
  en cascade implicite).
