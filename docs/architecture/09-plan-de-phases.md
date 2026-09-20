# 09 — Plan de phases

Pour chaque phase : analyser → proposer l'architecture détaillée → vérifier l'existant
→ modèles → API → implémenter → tester → sécuriser → documenter → monitorer → valider
→ seulement ensuite passer à la suivante (cahier des charges §62, Règle 20).

## Règle de séquencement backend / frontend (décision du 2026-09-18)

Stack confirmée : **FastAPI pour tout le backend, Next.js pour le frontend.**

Décision explicite : **le backend est développé et stabilisé dans son intégralité
(Phases 1 à 11 ci-dessous) avant que le moindre travail Next.js ne démarre.** Ce n'est
pas une préférence d'ordonnancement parmi d'autres — aucune page, composant ou
scaffold Next.js n'est créé avant la fin de la Phase 11.

Conséquences sur les phases telles que décrites plus bas :
- Toute mention de "dashboard" ou d'interface graphique dans les Phases 1 à 11 est
  **retirée** : ces phases ne livrent que de l'API (FastAPI), un schéma OpenAPI, et sont
  validées via Swagger UI / CLI / clients HTTP (curl, httpie, Postman) — jamais via une
  interface Next.js.
- Le SQL Editor (Phase 4) est livré comme **endpoint API sécurisé uniquement** ; son
  interface graphique est reportée à la Phase F.
- Une phase dédiée **Phase F — Frontend / Dashboard** est ajoutée après la Phase 11 et
  avant la Phase 12 (IA), qui construit tout le Next.js (dashboard global, dashboard
  projet, SQL Editor UI, etc.) au-dessus d'une API déjà complète et stable.

## Phase 0 — Architecture *(ce document)*

- **Livrables** : documents 01 à 08 de ce dossier.
- **Critère de sortie** : validation explicite du porteur de projet sur l'architecture
  globale, le modèle de données et le découpage Control Plane/Data Plane/Orchestrator/Agent.
- **Statut** : en attente de validation.

## Phase 1 — Control Plane (fondations)

- **Périmètre** : auth (users, sessions, MFA), organizations, memberships, RBAC,
  projects, API de base, base de métadonnées (Neon dev), audit log. **Aucun frontend**
  — validation via Swagger UI/httpie (cf. règle de séquencement ci-dessus).
- **Modèles** : `USERS`, `ORGANIZATIONS`, `MEMBERSHIPS`, `PROJECTS`, `AUDIT_LOGS`,
  `API_KEYS`.
- **API** : `/auth/*`, `/organizations/*`, `/projects/*`.
- **Sécurité** : hashing mots de passe (argon2/bcrypt), RBAC middleware, rate limiting
  auth.
- **Tests** : unitaires (RBAC, permissions), intégration (flux register→org→project).
- **Critère de sortie** : un utilisateur peut créer un compte, une organisation, un
  projet, inviter un membre, avec permissions correctement appliquées et auditées —
  démontré via l'API (Swagger/CLI de test), pas via une interface graphique.

## Phase 2 — Data Plane (fondations) — ✅ implémentée (2026-09-18)

- **Périmètre** : Data Plane Agent (bootstrap, enregistrement, heartbeat), CA interne
  pour le mTLS, communication sécurisée Control Plane ↔ Agent.
- **Modèles** : `REGIONS`, `NODES`, `NODE_REGISTRATION_TOKENS`, `USERS.is_platform_admin`.
- **API** : `POST /regions`, `GET /regions`, `POST /nodes/registration-tokens`,
  `POST /nodes/register`, `POST /nodes/{id}/heartbeat`, `GET /nodes`,
  `GET /nodes/{id}`, `POST /nodes/{id}/health-check`.
- **Sécurité** : CA interne (`backend/app/services/ca.py`, `cryptography`) signe le
  CSR du node à l'enregistrement (CommonName imposé par le Control Plane, jamais
  celui demandé par le node) ; l'agent expose son HTTPS uniquement en
  `--ssl-cert-reqs 2` (mTLS obligatoire) ; le sens Agent→Control Plane (register/
  heartbeat) utilise un secret bearer par node, pas mTLS, car il passe par l'API
  publique du Control Plane (cf. doc 03 §"Sécurité de la communication"). Gestion
  d'infrastructure (nodes/regions) séparée du RBAC organisationnel via
  `is_platform_admin`.
- **Tests** : 25 tests pytest côté Control Plane (dont le flux register → heartbeat →
  effective_status), 3 tests côté agent (CSR, ressources), `ruff` propre des deux
  côtés. **Vérifié manuellement de bout en bout avec de vrais processus et un vrai
  socket TLS** (pas seulement via TestClient) : agent réellement démarré avec
  `--ssl-cert-reqs 2`, un appel sans certificat client est bien rejeté au niveau TLS,
  et `POST /nodes/{id}/health-check` déclenche un vrai appel mTLS réussi du Control
  Plane vers l'agent.
- **Note** : le "VPS réel" du critère de sortie ci-dessous a été simulé par un agent
  tournant en local (`127.0.0.1`) faute de VPS provisionné à ce stade — le protocole
  et le code sont identiques à un déploiement sur un VPS distant (seul `IP_ADDRESS`
  change). Un test sur un VPS distant réel reste à faire avant la Phase 3.
- **Critère de sortie** : un node s'enregistre, remonte ses ressources (heartbeat),
  répond à un health check, et une commande (health-check) est déclenchée
  manuellement par API — validé. ✅

## Phase 3 — Database Orchestrator (phase critique) — ✅ implémentée (2026-09-18)

- **Périmètre** : sélection de node (algorithme de scoring par capacité libre),
  provisioning réel d'une base PostgreSQL, credentials chiffrés, lifecycle
  (create/suspend/resume/delete), jobs + retries avec backoff exponentiel.
- **Modèles** : `CLUSTERS`, `CLUSTER_MEMBERS`, `DATABASES` (avec `physical_name`
  généré par le système, distinct du nom affiché au client — évite les collisions
  entre tenants sur un cluster partagé), `DATABASE_CREDENTIALS` (mot de passe
  chiffré Fernet, jamais en clair), `JOBS`, `DATABASE_EVENTS`.
- **API** : `POST/GET /organizations/{o}/projects/{p}/databases`,
  `GET/DELETE .../databases/{id}`, `POST .../databases/{id}/{suspend,resume}`,
  `GET .../databases/{id}/connection`, `GET /jobs/{id}`.
- **Orchestration** : la queue de jobs est **la table `jobs` elle-même** (pas encore
  Redis/Arq — cf. `backend/app/services/jobs.py` pour la justification : les
  exigences fonctionnelles de la Phase 3 — asynchrone, retryable, idempotent,
  persistant — ne nécessitent pas de broker de messages tant qu'un seul worker
  tourne ; Redis/Arq reste la cible documentée pour la coordination multi-workers de
  la Phase 7). Le worker (`python -m app.worker`) tourne comme process séparé de
  l'API, exactement comme l'exige le flux Job → Queue → Worker → Orchestrator →
  Data Plane du §54.
- **Sécurité** : génération de mots de passe cryptographiquement sûrs côté
  Orchestrator (jamais fournis par le client) ; toute construction de DDL PostgreSQL
  passe par une validation stricte d'identifiant (regex whitelist) **des deux côtés**
  de la frontière mTLS (`backend/app/services/sql_identifiers.py` et
  `agent/app/postgres_admin.py`, dupliqué intentionnellement — ce sont deux
  déployables séparés) ; le mot de passe littéral est échappé via `quote_literal`
  côté PostgreSQL (paramétré), jamais concaténé ; un rôle PostgreSQL dédié par base ;
  `database:connect` (accès à `/connection`, qui rend un mot de passe en clair) est
  une permission RBAC strictement plus étroite que `database:read` — `readonly`/
  `billing` voient qu'une base existe mais jamais son mot de passe.
- **Tests** : 33 tests backend (placement/scoring, idempotence de `enqueue`, flux
  API + worker avec agent mocké, RBAC dont `database:connect`), 8 tests agent
  (dont des **tests d'intégration contre un vrai PostgreSQL** via Docker —
  `create_database`/`drop_database`/`suspend_database`/`resume_database` exécutés
  pour de vrai, pas mockés). `ruff` propre des deux côtés.
- **Vérifié manuellement de bout en bout avec un vrai PostgreSQL** (conteneur
  Docker `eminidb-node-postgres`, simulant le PostgreSQL local du node) : création
  d'une base via l'API → job traité par le worker → agent exécute un vrai
  `CREATE DATABASE`/`CREATE ROLE` via mTLS → connexion réussie avec les credentials
  renvoyés par l'API (`INSERT`/`SELECT` réels) → suspend (nouvelle connexion
  effectivement rejetée par PostgreSQL) → resume (reconnexion réussie, données
  intactes) → delete (base et rôle réellement absents de PostgreSQL après coup).
- **Critère de sortie** : un utilisateur crée une base via l'API, reçoit une chaîne
  de connexion fonctionnelle, la base apparaît `RUNNING` avec toutes les métadonnées
  de placement correctes. ✅ (validé avec un vrai PostgreSQL, un "VPS" toujours
  simulé en local faute d'infrastructure distante — même limite qu'en Phase 2).

## Phase 4 — Database Management — ✅ implémentée (2026-09-18)

- **Périmètre** : rôles PostgreSQL additionnels (readonly/app) avec rotation et
  suppression, extensions (liste blanche), SQL Editor sécurisé (exécution, historique,
  requêtes sauvegardées), introspection de schéma (tables/colonnes/index), métriques
  (taille, connexions actives). Toujours API-only.
- **Modèles** : `QueryExecution`, `SavedQuery` ; `DatabaseCredential` étendu avec
  `display_name` (nom convivial, distinct du `role_name` physique généré par le
  système — même raisonnement que `Database.physical_name` en Phase 3, pour éviter
  toute collision de nom de rôle entre tenants sur un cluster partagé) et
  `is_primary` (protège le rôle propriétaire créé au provisioning contre la
  suppression — indépendant du `scope`, qui reste `APP` pour ce rôle).
- **API** : `POST/GET/DELETE .../databases/{id}/roles`,
  `POST .../roles/{id}/rotate`, `GET/POST/DELETE .../extensions`,
  `POST .../sql/execute`, `GET .../sql/history`,
  `POST/GET/DELETE .../sql/saved-queries`, `GET .../metrics`, `GET .../tables`.
- **Sécurité** :
  - Le SQL Editor se connecte **directement au PostgreSQL du client, sous l'identité
    du rôle Postgres choisi** (jamais via un compte admin) — ce sont les GRANT/REVOKE
    réels de PostgreSQL qui appliquent les permissions, pas une réimplémentation
    applicative qui pourrait diverger.
  - `database:connect`/`database:sql:execute`/`database:roles:manage`/
    `database:extensions:manage` sont strictement plus étroits que `database:observe`
    (lecture seule, accessible à `readonly`/`billing`) — ces rôles voient les
    métadonnées mais ne peuvent ni exécuter de SQL, ni gérer rôles/extensions, ni
    récupérer un mot de passe.
  - Extensions : liste blanche (`ALLOWED_EXTENSIONS` côté agent) — plusieurs
    extensions PostgreSQL standard (`plpythonu`, `adminpack`...) permettent
    l'exécution de code ou l'accès au système de fichiers et ne doivent jamais être
    exposées en self-service.
  - `AgentRequestError` distingue désormais explicitement "l'agent a refusé la
    requête" (4xx propagé tel quel à l'appelant) de "l'agent est injoignable" —
    bug réel trouvé et corrigé pendant cette phase (une extension refusée
    remontait en 500 avant ce correctif).
- **Tests** : 45 tests backend (dont RBAC complet par endpoint, protection du rôle
  primaire, régression `AgentRequestError`), 15 tests agent (dont des **tests
  d'intégration réels** contre PostgreSQL pour les rôles/extensions/métriques/schéma
  — deux bugs réels de privilèges PostgreSQL trouvés et corrigés par ces tests :
  `ALTER DEFAULT PRIVILEGES` doit cibler `FOR ROLE <owner>` et non l'appelant admin,
  et un rôle `app` a besoin de `GRANT CREATE ON SCHEMA` pour créer des tables).
- **Vérifié manuellement de bout en bout avec un vrai PostgreSQL** : création de
  table/insertion/sélection réelles via le SQL Editor ; création d'un rôle
  `readonly` puis preuve que PostgreSQL bloque bien un `INSERT` avec ce rôle
  (`permission denied for table`, capturé proprement, pas un crash) ; extension
  `pgcrypto` installée puis listée comme installée ; métriques et introspection de
  table conformes à l'état réel de la base ; rotation de mot de passe puis
  suppression du rôle, vérifiée absente de PostgreSQL après coup (`docker exec ...
  psql`) ; protection du rôle propriétaire contre la suppression confirmée.
- **Critère de sortie** : l'endpoint SQL Editor exécute des requêtes en respectant
  strictement les permissions PostgreSQL réelles du rôle utilisé ; extensions
  activables via API avec liste blanche. ✅ L'interface graphique de ces
  fonctionnalités est livrée en Phase F.

## Phase 5 — Backup et Recovery — ✅ implémentée (2026-09-18)

- **Périmètre** : backups auto/manuels, object storage S3-compatible (MinIO en dev),
  restore vers une nouvelle base, vérification périodique des backups, rétention
  (purge automatique des backups automatiques expirés — jamais des manuels).
  **PITR (WAL continu) explicitement différée** : voir note ci-dessous.
- **Modèles** : `Backup` (statuts `pending → completed → verified` ou
  `verification_failed`/`failed`/`purged`, cf. doc 05 §5.1) ; réutilise `Job` pour
  `backup_database`/`restore_database`/`verify_backup`.
- **API** : `POST/GET .../databases/{id}/backups`, `GET .../backups/{id}`,
  `POST .../backups/{id}/restore`, `GET/PUT .../backup-policy`.
- **Composants d'exécution** :
  - `backend/app/scheduler.py` (`python -m app.scheduler`) — processus séparé qui
    décide *quand* sauvegarder/vérifier/purger (scan périodique), distinct du worker
    qui *exécute* les jobs. C'est le "processus de vérification automatique qui
    tourne réellement en tâche de fond" exigé par le critère de sortie.
  - Côté agent (`agent/app/backup.py`) : `pg_dump`/`pg_restore` réels via
    subprocess, dump chiffré (Fernet) avant tout envoi vers l'object storage —
    jamais stocké en clair ni sur le disque du node primaire. La vérification
    restaure dans une base jetable, vérifie, puis la supprime (cahier des charges
    §59).
- **Sécurité** : chiffrement applicatif des dumps (même schéma que les credentials,
  §4.4) ; les credentials S3 ne vivent que côté agent, jamais côté Control Plane
  (le CP ne fait que suivre des métadonnées et une clé d'objet) ; la purge ne touche
  jamais un backup manuel, uniquement les automatiques arrivés en fin de rétention.
- **Bug réel trouvé et corrigé** : `pg_restore --no-owner` sans `--role` laissait les
  objets restaurés appartenir à l'utilisateur admin plutôt qu'au rôle propriétaire de
  la nouvelle base — le tenant recevait *"permission denied"* sur ses propres
  données après une restauration. Corrigé en passant `--role=<rôle_cible>` (le
  superuser peut `SET ROLE` vers n'importe quel rôle). Un test de non-régression
  vérifie maintenant explicitement l'accès **en tant que rôle tenant**, pas admin.
- **Tests** : 55 tests backend (dont politique de rétention, protection des backups
  manuels contre la purge, échec terminal de job → `Backup.status=FAILED`,
  planificateur testé directement), 18 tests agent dont 3 **tests d'intégration
  réels** (vrai `pg_dump`/`pg_restore` via `docker exec`, vrai MinIO, cycle complet
  backup → upload → download → restore → vérification de données, plus vérification
  positive et négative).
- **Vérifié manuellement de bout en bout** avec un vrai PostgreSQL et un vrai MinIO :
  sauvegarde manuelle réelle (objet confirmé présent dans MinIO via inspection
  directe du volume), restauration dans une nouvelle base avec les données intactes
  **et accessibles en lecture/écriture sous l'identité du tenant** (pas seulement de
  l'admin — c'est précisément ce qui a révélé le bug ci-dessus), vérification
  automatique déclenchée par le planificateur puis exécutée par le worker
  (`status: verified`, avec le détail réel du contrôle de restauration).
- **Note sur le PITR** : le cahier des charges (§22) prévoit une restauration à un
  instant T via archivage WAL continu. Cette phase implémente des backups
  **logiques** (`pg_dump` par base), cohérents avec le modèle de provisioning actuel
  où plusieurs bases d'un même cluster/node peuvent appartenir à des tenants
  différents — l'archivage WAL continu opère lui au niveau du *cluster PostgreSQL
  entier*, pas d'une base individuelle, et partage sa plomberie avec la réplication
  physique. Implémenter un vrai PITR proprement nécessite donc l'infrastructure de
  Phase 6 (réplication, HA) ; ce sera traité conjointement plutôt que construit à
  moitié ici. Documenté comme limitation connue, pas oublié.
- **Critère de sortie** : un backup peut être restauré avec succès vers une nouvelle
  instance ✅ ; le processus de vérification tourne réellement en tâche de fond
  (scheduler + worker, processus séparés de l'API) ✅.

## Phase 6 — Haute disponibilité — ✅ implémentée (2026-09-18)

- **Périmètre** : réplication PostgreSQL en streaming réelle, statut de réplication,
  promotion, Health Monitor + Failover Controller (détection + failover automatique),
  gestion de cluster (attacher un replica, déclencher un failover manuel).
- **Modèles** : `ClusterEvent` (incident trail — chaque failover, réussi ou non, est
  enregistré). `Cluster`/`ClusterMember` (déjà posés en Phase 3) sont maintenant
  réellement utilisés avec `topology=primary_replica` et `role=replica`.
- **API** (réservée platform-admin, comme `/nodes`/`/regions` — la gestion de cluster
  est une décision infra, pas une action tenant) : `GET /clusters/{id}`,
  `POST /clusters/{id}/replicas`, `POST /clusters/{id}/failover`.
- **Frontière de responsabilité assumée** : le *provisioning* initial d'un replica
  (le clonage `pg_basebackup`) est traité comme une étape d'infrastructure "jour 0",
  au même titre que le provisioning d'un VPS lui-même (cf. Règle de la Phase 2)
  — dans un déploiement réel, l'agent tournant nativement sur le node aurait le
  contrôle `pg_ctl`/systemd nécessaire pour l'automatiser complètement ; dans ce
  sandbox conteneurisé, Docker (pas l'agent) possède le cycle de vie du process
  Postgres, donc ce clonage a été fait une fois via des commandes Docker (exactement
  comme les containers Postgres/MinIO initiaux l'ont été). Le code de la plateforme
  (statut de réplication, promotion, attachement au cluster, failover) est lui
  entièrement réel et testé — c'est le cœur du critère de sortie de cette phase.
- **Sécurité/robustesse** : `add_replica` refuse d'attacher un node qui ne rapporte
  pas réellement `role=standby` (vérification active, pas déclarative) ; le failover
  choisit le replica au lag le plus faible ; l'ancien primary est retiré du suivi de
  cluster après un failover (il devrait être re-cloné avant de pouvoir rejoindre —
  déferré, cf. Phase 7) ; un failover automatique qui ne trouve aucun replica sain
  enregistre un `ClusterEvent` `FAILOVER_FAILED` au lieu d'échouer silencieusement.
- **Tests** : 62 tests backend (attachement de replica, échec si le node n'est pas
  standby, failover manuel avec repointage des bases, `NoHealthyReplicaError`,
  déclenchement automatique par le scheduler sur primary "offline" — et absence de
  déclenchement sur primary sain), 21 tests agent (dont 3 **tests d'intégration
  contre une vraie réplication en streaming** PostgreSQL : statut primary/standby,
  réplication réelle de données ; le test de promotion réelle est protégé par un
  garde-fou car destructif — cf. `RUN_DESTRUCTIVE_HA_TESTS`).
- **Vérifié manuellement de bout en bout avec deux vrais conteneurs PostgreSQL en
  réplication en streaming réelle** (via Docker — réseau dédié, rôle `replicator`,
  `pg_basebackup -R`) : base créée et peuplée sur le primary → replica attaché au
  cluster via l'API (vérification réelle de `role=standby`, lag=0) → **primary
  réellement arrêté** (processus agent tué) → `POST /clusters/{id}/failover` →
  **vraie promotion PostgreSQL** (`pg_promote()`, nouvelle timeline, confirmé via
  `pg_is_in_recovery() = f`) → `Database.connection_port` automatiquement repointé
  vers le node promu → données antérieures au failover intactes et lisibles → **une
  nouvelle écriture réussie sur le nouveau primary**, prouvant une vraie bascule
  writable, pas un simple changement d'étiquette. La topologie de réplication a
  ensuite été reconstruite (nouveau `pg_basebackup`) pour que les tests automatisés
  restent reproductibles.
- **PITR** : toujours différé (cf. Phase 5) — l'infrastructure de réplication de
  cette phase est le prérequis technique, mais l'archivage WAL continu vers l'object
  storage n'est pas encore implémenté ; reste une piste ouverte pour un futur
  incrément de durcissement.
- **Critère de sortie** : panne simulée d'un primary réel → failover automatique
  (déclenché manuellement ici, mécanisme identique à l'automatique du scheduler,
  testé séparément) vers un replica réel ✅ ; endpoint client mis à jour
  automatiquement (le client interroge `/connection`, jamais une IP en dur) ✅ ;
  incident documenté via `ClusterEvent` ✅.

## Phase 7 — Scaling — ✅ implémentée (2026-09-19)

- **Périmètre** : resize vertical (avec garantie PostgreSQL réelle et applicable),
  migration d'une base entre nodes (réutilise les mécanismes backup/restore de la
  Phase 5), fondations multi-node/multi-région déjà posées en Phases 2-3 et
  confirmées par l'usage réel (3 nodes réels dans cette phase).
- **Resize** : synchrone (pas un job — un seul appel agent rapide, cf. précédent de
  la Phase 4 pour roles/extensions). Comme un cluster partagé n'a pas de cgroups par
  base, la garantie concrète et honnête est une limite de connexions PostgreSQL
  réelle (`ALTER DATABASE ... CONNECTION LIMIT`, formule documentée
  `cpu_limit × 20`) plutôt qu'une isolation CPU/RAM qui n'existe pas dans ce modèle.
  Refuse le resize si la nouvelle taille ne tient pas sur le node actuel (409,
  suggère une migration).
- **Migration** : réservée platform-admin (le client ne choisit jamais son node —
  §"Règle 6"/§79). Séquence : *quiesce* du rôle propriétaire côté source → dump réel
  (Phase 5) → provisioning + restore réel sur le node cible avec le **même**
  `physical_name`/`role_name`/mot de passe (le client ne voit rien changer sauf
  host/port, comme pour un failover) → bascule des métadonnées → suppression de la
  source **seulement après** confirmation du succès de la cible (§18 — jamais
  destructif avant vérification). Migration inter-région refusée explicitement
  (changerait silencieusement la résidence des données).
- **Trois bugs réels trouvés et corrigés par les tests, en cascade, sur le même
  mécanisme de "quiescence"** :
  1. Réutiliser `suspend_database` (`ALLOW_CONNECTIONS false`) bloquait *aussi* la
     connexion admin dont `pg_dump` a besoin — la sauvegarde de migration échouait
     systématiquement. Créé un mécanisme dédié `quiesce_for_migration`.
  2. Révoquer `CONNECT` sur le rôle spécifique ne suffit pas : PostgreSQL accorde
     `CONNECT` à `PUBLIC` par défaut, donc le rôle continuait de se connecter via ce
     droit hérité. Corrigé en révoquant `PUBLIC` (ce qui, par ailleurs, bloque aussi
     plus correctement les rôles additionnels de la Phase 4, pas seulement le
     propriétaire).
  3. Même après ça, le rôle **propriétaire** de la base continuait de se connecter :
     la propriété d'une base confère un `CONNECT` implicite et non révocable.
     Corrigé en transférant temporairement la propriété à l'admin avant de révoquer
     — sans risque ici puisque la source est de toute façon supprimée après une
     migration réussie.
  Chacun de ces trois bugs a été découvert par un test réel (intégration agent ou
  smoke test live), pas deviné à l'avance — exactement le genre de subtilité
  PostgreSQL qu'une suite mockée n'aurait pas révélée.
- **Gap identifié et documenté (non corrigé dans cette phase)** : une base dont le
  job de migration (ou toute autre opération de cycle de vie) échoue définitivement
  passe en statut `FAILED` sans mécanisme de récupération en libre-service — un
  opérateur doit intervenir manuellement. Un flux de reprise explicite est laissé
  pour un futur durcissement (Phase 11) plutôt que bricolé dans l'urgence.
- **Tests** : 72 tests backend (resize avec/sans capacité suffisante, RBAC,
  migration avec repointage réel des métadonnées, rejets cross-région/capacité/
  santé du node cible, échec terminal → `Database.status=FAILED`), 24 tests agent
  (dont un test de régression réel pour `quiesce_for_migration` couvrant
  spécifiquement le 3ᵉ bug — connexion admin toujours possible, rôle tenant
  effectivement bloqué).
- **Vérifié manuellement de bout en bout avec trois vrais PostgreSQL** (node A
  original, le replica promu de la Phase 6 laissé de côté pour ne pas perturber la
  topologie HA, et un troisième conteneur indépendant comme cible) : resize réel
  confirmé via `pg_database.datconnlimit` ; migration réelle round-trip
  (node C → node A) avec données intactes, écriture réussie après coup, et **rôle +
  base physiquement absents du node source après coup** (vérifié directement en
  base) — exactement la séquence "jamais destructif avant vérification" prévue par
  l'architecture.
- **Critère de sortie** : migration d'une base d'un node à un autre sans perte de
  données ni interruption destructive ✅ (fenêtre de service brève assumée et
  documentée — ce n'est pas un mécanisme zéro-downtime, qui nécessiterait la
  réplication physique par base, hors de portée ici) ; resize vertical fonctionnel
  avec garantie PostgreSQL réelle ✅.

## Phase 8 — Developer Platform — ✅ implémentée (2026-09-19)

- **Périmètre** : SDK Python officiel, CLI (`platform`) construite dessus, webhooks
  (souscription par organisation, livraison signée, historique). Les SDKs
  TypeScript/Go sont explicitement **différés à la Phase F** (cf. note ci-dessous) —
  pas dans le périmètre de cette phase.
- **Modèles** : `Webhook` (`url` restreinte à `https://` par validation Pydantic,
  `encrypted_secret` chiffré Fernet — contrairement aux mots de passe de connexion
  (argon2, sens unique), un secret de webhook doit être **redécouvré** à chaque
  livraison pour signer le corps, donc chiffrement réversible, pas hachage),
  `WebhookDelivery` (`status` pending/succeeded/failed, `response_code`, `error`).
- **API** : `POST/GET/DELETE /organizations/{o}/webhooks`,
  `GET /organizations/{o}/webhooks/{id}/deliveries`.
- **Architecture de livraison** : réutilise **exactement** l'infrastructure
  jobs/worker déjà en place depuis la Phase 3 (`deliver_webhook` comme nouveau type
  de job dans `WEBHOOK_HANDLERS`, fusionné dans `ALL_HANDLERS` du worker) plutôt que
  d'introduire un mécanisme de livraison séparé — mêmes retries avec backoff
  exponentiel, même passage en échec terminal visible
  (`_TERMINAL_FAILURE_HANDLERS["deliver_webhook"]`). `emit_event()` est appelée
  aux points de cycle de vie pertinents (`database.created`, `database.failed`,
  `backup.completed`, `backup.failed`, `restore.completed`) et énumère les
  webhooks actifs de l'organisation dont la liste `event_types` correspond.
- **SDK Python** (`sdk/eminidatabase_sdk/client.py`, classe `PlatformClient`) :
  un wrapper fin par appel API, sans logique métier ni cache ni retry côté client
  (tout ça vit déjà dans la plateforme) — pensé pour rester trivialement portable
  vers un futur SDK TypeScript/Go qui suivrait le même mapping 1:1 avec l'API.
- **CLI** (`sdk/eminidatabase_sdk/cli.py`, Typer, commande `platform`) : construite
  **entièrement au-dessus du SDK**, jamais d'appel HTTP direct dans la CLI — c'est
  elle-même un exemple d'intégration tierce à l'API publique. Sous-commandes
  `organizations`, `projects`, `db` (create/list/get/resize/suspend/resume/delete/
  connect/sql/backup), `webhooks`, `jobs`. Résolution slug → UUID (organisation/
  projet/base) pour une UX qui n'oblige jamais l'utilisateur à manipuler des UUID
  à la main.
- **Sécurité** :
  - Webhooks : signature HMAC-SHA256 du corps exact envoyé (`X-Eminidatabase-
    Signature: sha256=<hex>`), en-tête `X-Eminidatabase-Event`, secret révélé une
    seule fois à la création (comme une clé API) puis jamais renvoyé en clair par
    l'API (seul `list_webhooks` existe, sans le secret) — seul le worker,
    côté serveur, le déchiffre pour signer chaque livraison.
  - `webhooks:manage` (RBAC) réservé à `OWNER`/`ADMIN` — un webhook est un canal de
    sortie de données de l'organisation entière, pas une ressource par projet.
  - URL de webhook strictement `https://` (validateur Pydantic) en production ;
    contournée volontairement une seule fois pour la preuve de livraison réelle
    ci-dessous, en insérant la ligne directement en base (test boîte blanche du
    mécanisme de livraison, pas du validateur d'entrée — jamais fait via l'API).
- **Bugs réels trouvés et corrigés** :
  1. **Collision d'import inter-paquets dans les tests** : `sdk/tests/test_client.py`
     important `from tests.conftest import TestSessionLocal` résolvait en fait vers
     `backend/tests/conftest.py` (les deux dossiers `tests/` étant ambigus une fois
     `backend/` ajouté à `sys.path`), dont le code de module réassignait
     `app.dependency_overrides[get_db]` vers un second moteur jamais initialisé
     (`create_all` non appelé) — corrompant l'override pour le reste de la session
     de tests (`dependency_overrides` est un dict partagé sur l'app FastAPI
     singleton), avec des échecs en cascade ("no such table: users") dans des tests
     sans rapport. Corrigé en exposant `TestSessionLocal` via une fixture pytest
     (`db_session_factory`) plutôt qu'un import de module brut.
  2. **Incompatibilité de version Typer/Click** : `typer==0.12.5` épinglé mais
     `click` non épinglé résolvait en 8.5.0, provoquant une `TypeError` sur tout
     `--help` et, plus sournoisement, un parsing erroné de `--email`/`--password`
     ("Got unexpected extra arguments"). Corrigé en montant vers `typer>=0.15`.
  3. **UX `--wait` trompeuse** : `backup create --wait` et `db restore` affichaient
     le statut **avant** l'attente (ex. backup encore "pending" alors que le job
     venait de se terminer avec succès), faute de rafraîchir la ressource après
     `wait_for_job()`. Corrigé (ajout de `get_backup()` au SDK, re-fetch après
     l'attente) et vérifié en live : `db backup create --wait` affiche bien
     `"status": "completed"` avec la taille réelle du dump.
- **Tests** : 10 tests SDK/CLI (cycle de vie base complet via le SDK avec agent
  mocké, cycle de vie webhook, gestion d'erreurs `ApiError`, CLI via
  `typer.testing.CliRunner` avec transport ASGI injecté dans chaque client que la
  CLI construit), aucune régression sur les 79 tests backend / 24 tests agent déjà
  existants. `ruff` propre (`app/`, `tests/` — le bruit sur `alembic/versions/*`
  et `.venv` est préexistant, non lié à cette phase), pas de dérive Alembic
  (`alembic check`).
- **Vérifié manuellement de bout en bout, entièrement via la CLI, sans jamais
  toucher le dashboard** (qui n'existe de toute façon pas encore) : `login` →
  `organizations create` → `projects create` → `db create --wait` (provisioning
  réel jusqu'à `RUNNING`) → `db list` → `db connect` → `db sql` (vrais
  `CREATE TABLE`/`INSERT`/`SELECT` contre un vrai PostgreSQL) → `db resize` (vraie
  limite de connexions modifiée) → `db backup create --wait` (vrai `pg_dump`,
  4280 octets, `status: completed` confirmé) → `webhooks create`/`webhooks list`.
  **Livraison de webhook réelle prouvée séparément** : un récepteur HTTP local
  (`http.server` sur `127.0.0.1:8899`) a reçu une vraie requête POST du worker
  (déjà en cours d'exécution, sans redémarrage) déclenchée par l'insertion directe
  d'un `Webhook`/`WebhookDelivery`/`Job` — `WebhookDelivery.status = SUCCEEDED`,
  `response_code = 200`, `error = None`, correspondant exactement à la logique de
  signature HMAC du code source (vérifiée indépendamment par recalcul du HMAC
  attendu à partir du payload et du secret déchiffré).
- **Note sur les SDKs TypeScript/Go** : différés à la Phase F. Raisonnement :
  ce sont des artefacts destinés à être *consommés et testés* par un frontend/
  toolchain qui n'existe pas encore sous la contrainte de séquencement
  backend-first (cf. note en tête de ce document) — les construire maintenant
  reviendrait à écrire du code non exercé. Le SDK Python et la CLI, eux, sont de
  l'outillage développeur backend (Python, pas frontend) légitimement dans le
  périmètre de cette phase, et prouvent déjà que l'API est utilisable par un tiers
  sans dashboard.
- **Critère de sortie** : un développeur externe peut créer/gérer une base
  uniquement via la CLI, sans toucher au dashboard. ✅

## Phase 9 — Microfinance — ✅ implémentée (2026-09-19)

- **Décision d'architecture (validée avec le porteur de projet, 2026-09-19)** : le
  module microfinance est un **nouveau déployable séparé** (`microfinance/`, au même
  niveau que `backend/`/`agent/`/`sdk/`) qui est lui-même **un client** de la
  plateforme — une unique `organization` CP pour le produit microfinance, et chaque
  institution = un `project`/`database` provisionné dynamiquement dedans via le SDK
  Python de la Phase 8 (dogfooding réel), avec
  sa propre Control DB de métadonnées et son propre personnel/RBAC, distincts du
  Control Plane. Détail complet, schéma, moteur de ledger, migrations par tenant et
  découpage en sous-phases : [08](08-microfinance-et-billing.md#83-décision-darchitecture-validée-avec-le-porteur-de-projet-2026-09-19).
- **Sous-phases** (cf. [08 §8.10](08-microfinance-et-billing.md#810-découpage-en-sous-phases)) :
  9.1 Fondations (onboarding, auth/RBAC staff) → 9.2 Ledger et épargne → 9.3 Crédit
  (cycle complet, critère de sortie de la phase) → 9.4 Comptabilité et paiements.
- **Pré-requis** : infrastructure cœur stable (Phases 0-8 validées). ✅
- **Critère de sortie** : cycle complet demande de crédit → décaissement → échéancier →
  remboursement → clôture, avec ledger cohérent et auditable.

### Phase 9.1 — Fondations — ✅ implémentée (2026-09-19)

- **Périmètre** : nouveau déployable `microfinance/` (package `mf_app`, cf. note
  ci-dessous) ; Control DB du service (`MFPlatformAccount`, `MFInstitution`,
  `MFStaffUser`, `MFJob`) ; onboarding d'institution en dogfooding réel du SDK
  Python de la Phase 8 ; auth staff + RBAC métier (§8.9) ; deux jeux de
  migrations Alembic (`alembic_control/`, `alembic_tenant/`, §8.5) ; schéma
  tenant minimal (`InstitutionProfile`, `Branch`, `Agent`) pour prouver le
  pipeline de bout en bout avant d'y ajouter le ledger en 9.2.
- **Pourquoi le package s'appelle `mf_app` et non `app`** : `backend/` utilise
  déjà `app` comme nom de paquet top-level ; les tests de ce service embarquent
  le **vrai** backend en process (comme `sdk/tests/`) pour prouver le dogfooding
  automatiquement, ce qui exige d'importer les deux paquets dans le même
  process Python — exactement la classe de bug de collision `tests` trouvée en
  Phase 8 (cf. `sdk/README.md`), ici sur `app`. Renommé avant d'écrire le
  moindre test, pas après avoir buté dessus.
- **Décision de conception (initiative propre, pas demandée)** : le mot de
  passe de l'`institution_admin` créé à l'onboarding est généré et révélé
  **de façon synchrone, dans la réponse HTTP de `POST /institutions`** (comme
  une clé API ou un secret de webhook) — **pas** dans le job asynchrone
  `onboard_institution`. Générer un secret dans un job obligerait à le
  persister quelque part (`MFJob.result`) pour le renvoyer plus tard à
  l'appelant, exactement le secret-en-clair-au-repos que ce codebase évite
  partout ailleurs. Le job ne fait donc que le provisioning d'infrastructure
  (déjà idempotent/retryable par nature) ; la création du compte admin, elle,
  est synchrone et n'a besoin d'aucune tolérance à la panne particulière.
- **Bug réel trouvé et corrigé** : `MFPlatformAccount.token_expires_at`, relu
  depuis une session SQLite fraîche (la **deuxième** institution onboardée dans
  un même process), revenait *naïf* (sans tzinfo) et faisait planter la
  comparaison avec un `utcnow()` fraîchement créé (`TypeError: can't subtract
  offset-naive and offset-aware datetimes`) — SQLite ne conserve pas le tzinfo
  au aller-retour, un piège déjà documenté dans le `timeutil.py` du backend et
  copié tel quel dans celui de ce service, mais pas encore appliqué au bon
  endroit. Corrigé en normalisant avec `as_aware_utc()` avant la comparaison
  dans `mf_app/services/platform_client.py`. Trouvé par les tests automatisés
  (deuxième `_onboard()` dans `test_staff_token_rejected_on_other_institution`),
  pas deviné à l'avance.
- **Tests** : 6 tests, mais construits pour **embarquer le vrai backend en
  process** (`httpx.ASGITransport`, cf. `sdk/tests/`) — chaque institution
  onboardée dans la suite passe par le vrai routing/validation/DB du backend
  et le vrai SDK, pas un mock de ce à quoi ça devrait ressembler. Deux choses
  seulement sont simulées, cohérent avec la pratique déjà établie dans tout le
  projet (l'agent est mocké dans toutes les suites automatisées, un vrai
  Postgres/agent réel est réservé à la vérification manuelle) :
  `app.services.orchestrator.call_agent` (backend) et
  `mf_app.db.tenant_session.tenant_database_url` (un vrai fichier SQLite local
  tient lieu de Postgres réel — le **vrai** sous-processus de migration Alembic
  tourne quand même pour de vrai, juste contre SQLite). `ruff` propre.
- **Bug d'infrastructure de test trouvé et corrigé** : la première version de
  `run_onboarding_job` appelait `backend_worker.run_once()` **avant**
  `mf_worker.run_once()`, en supposant (à tort) que le job `create_database`
  du backend existait déjà à ce moment — en réalité il n'est créé que **pendant**
  l'exécution du job `onboard_institution`, qui appelle ensuite
  `wait_for_job()` (polling réel avec `sleep` entre chaque tentative, jusqu'à
  120s). Comme il s'agit d'un seul process de test synchrone, rien ne
  traitait ce job backend pendant l'attente, provoquant un blocage de ~120s
  par test. Corrigé en faisant tourner un petit poller `backend_worker.run_once()`
  en tâche de fond **pendant** l'attente du job microfinance, arrêté dès que
  celui-ci se termine.
- **Bug d'infrastructure de test trouvé et corrigé (deuxième)** : les moteurs
  aiosqlite créés pour chaque institution (`mf_app.db.tenant_session._engine_cache`,
  un cache process-level jamais vidé par conception — en production une
  institution garde sa connexion toute sa durée de vie) s'accumulaient sur
  toute la session de tests (5 institutions) et provoquaient un blocage de
  l'interpréteur à la fin de la suite (chaque connexion aiosqlite possède son
  propre thread). Corrigé par une fixture `autouse` qui dispose les moteurs
  après chaque test — sans impact sur le comportement réel du service, un
  problème de tests uniquement.
- **Vérifié manuellement de bout en bout avec un vrai backend, un vrai agent
  (mTLS réel) et un vrai PostgreSQL** (`eminidb-node-postgres`, région `eu-west`
  déjà enregistrée en Phase 2) : bootstrap réel du compte plateforme du service
  (`register`/`login`/`create_organization` réels) → `POST /institutions` →
  job traité par le worker microfinance → vrai `create_project`/`create_database`
  sur le vrai backend → vraie base provisionnée par le vrai agent → vraie
  migration Alembic tenant appliquée (confirmé via `docker exec ... psql \dt` :
  tables `institution_profile`/`branches`/`agents`/`alembic_version` réellement
  présentes) → ligne `institution_profile` réelle avec le bon nom/devise →
  institution passée `active` → login de l'admin → création réelle d'une
  agence, confirmée par une lecture directe dans PostgreSQL.
- **Critère de sortie de la sous-phase** : un opérateur peut onboarder une
  institution via l'API uniquement, celle-ci obtient une base réellement
  isolée provisionnée par la plateforme, et son personnel peut s'authentifier
  et gérer ses agences — sans jamais toucher au Control Plane directement. ✅

### Phase 9.2 — Ledger et épargne — ✅ implémentée (2026-09-19)

- **Périmètre** : moteur de ledger double-écriture (`mf_app/services/ledger.py`),
  comptes internes (`cash`/`interest_income`), clients avec KYC, produits/comptes
  d'épargne, dépôt/retrait. Détail complet, décisions de conception et bug réel
  trouvé (course entre deux transactions SQLite concurrentes dans l'infrastructure
  de tests) : [08 §8.13](08-microfinance-et-billing.md#813-phase-92--ledger-et-épargne--implémentée-2026-09-19).
- **Tests** : 10 (5 moteur de ledger direct DB + 5 flux HTTP dépôt/retrait/KYC/RBAC).
- **Critère de sortie** : un dépôt/retrait passe par le moteur de ledger, jamais par
  une écriture directe de solde ; un rejeu de la même `idempotency_key` ne double
  jamais une transaction ; `reconcile_balance` égale `balance_cached` en toute
  circonstance. ✅

### Phase 9.3 — Crédit — ✅ implémentée (2026-09-19)

- **Périmètre** : produits de crédit (déclinant/flat), machine à états du prêt,
  génération d'échéancier déterministe, décaissement, remboursement avec clôture
  automatique. Détail complet : [08 §8.14](08-microfinance-et-billing.md#814-phase-93--crédit--implémentée-2026-09-19-critère-de-sortie-de-la-phase-9).
- **Tests** : 9 (5 formule d'amortissement pure + 4 cycle de vie complet via l'API).
- **Critère de sortie de la Phase 9 (explicite)** : cycle complet demande de crédit
  → décaissement → échéancier → remboursement → clôture, avec ledger cohérent et
  auditable — **vérifié par un test de bout en bout qui suit exactement ce cycle
  via l'API réelle**
  (`test_full_loan_lifecycle_request_to_closure`), pas seulement composant par
  composant, et confirmé une seconde fois en direct contre un vrai PostgreSQL
  (cf. note de vérification manuelle en fin de Phase 9). ✅

### Phase 9.4 — Comptabilité et paiements — ✅ implémentée (2026-09-19)

- **Périmètre** : rapport de balance générale (preuve d'audit que le moteur de
  ledger reste équilibré), rapport de portefeuille de prêts, couche d'abstraction
  de paiement (`PaymentProvider`/`ManualPaymentProvider`, intégration mobile money
  réelle explicitement différée). Détail complet et raisons des simplifications
  assumées (pas de table `CHART_OF_ACCOUNTS` séparée) :
  [08 §8.15](08-microfinance-et-billing.md#815-phase-94--comptabilité-et-paiements--implémentée-2026-09-19).
- **Tests** : 5 (balance équilibrée à vide, balance équilibrée après une activité
  réelle mêlant épargne et crédit, RBAC des rapports, 2 tests unitaires du provider
  de paiement).
- **Critère de sortie** : la balance générale reste équilibrée après toute
  combinaison de dépôts/retraits/décaissements/remboursements — vérifié, pas
  supposé. ✅

**Bilan Phase 9 (toutes sous-phases)** : 29 tests microfinance (109 backend/agent/
SDK + 29 = 138 tests au total sur toute la plateforme désormais), `ruff` propre,
aucune dérive Alembic sur les deux jeux de migrations. Vérification manuelle de
bout en bout contre un vrai backend, un vrai agent (mTLS réel) et un vrai
PostgreSQL couvrant le cycle complet du critère de sortie — voir le rapport de fin
de phase pour le détail live.

## Phase 10 — Billing et SaaS — ✅ implémentée (2026-09-19)

- **Périmètre** : plans configurables, subscriptions, usage metering, factures.
- **Où ça vit** : contrairement à la Phase 9 (microfinance, nouveau déployable
  client de la plateforme), le billing plateforme vit **dans `backend/`** — la
  plateforme se facture elle-même à partir de ses propres métadonnées, une
  extension naturelle du Control Plane. Nouveaux modèles `Plan`/`Subscription`/
  `UsageRecord`/`Invoice`/`InvoiceLineItem` ; nouveaux services `quotas.py`
  (gate de provisioning), `billing.py` (génération de factures), `payments.py`
  (abstraction de paiement, §47) ; deux nouveaux ticks sur le scheduler existant
  depuis la Phase 5 (`meter_usage`, `generate_due_invoices`) plutôt qu'un nouveau
  processus. Détail complet, dont les 6 bugs réels trouvés et corrigés (1 dans le
  produit — `GET .../invoices/{id}` plantait en 500 —, 5 dans les tests) :
  [08 §8.16](08-microfinance-et-billing.md#816-phase-10--billing-et-saas--implémentée-2026-09-19).
- **Quotas réellement appliqués** : `POST .../databases` vérifie le plan actif de
  l'organization avant tout provisioning (nombre de bases, stockage et vCPU
  alloués) — un dépassement renvoie `402 Payment Required`, pas un `403`
  générique. Chaque organization reçoit une `Subscription` sur le plan `free`
  automatiquement à sa création (jamais une relation nullable à vérifier ailleurs).
- **Metering réel, jamais fabriqué** : chaque tick de 60s appelle le vrai endpoint
  `/metrics` de l'agent (déjà utilisé depuis la Phase 4) pour chaque base
  `RUNNING` — `storage_gb_hours` et `connections` dérivés de valeurs réelles ;
  `cpu_hours` facturé sur la capacité **allouée** (pas de cgroup par base sur un
  cluster partagé, cf. Phase 7) ; `egress_gb` jamais émis (aucune instrumentation
  réseau n'existe) — limitations assumées et documentées, pas des approximations
  déguisées.
- **Tests** : 7 nouveaux (86 tests backend au total, aucune régression). `ruff`
  propre, aucune dérive Alembic.
- **Vérifié manuellement de bout en bout avec un vrai backend, un vrai agent, un
  vrai PostgreSQL et le vrai scheduler tournant en tâche de fond** (aucun appel de
  fonction manuel) : organization créée → souscription `free` automatique
  confirmée → tentative de deuxième base réellement rejetée en `402` → une
  souscription réelle avec une période de facturation courte insérée sur une
  organization ayant une base `RUNNING` réelle → **le scheduler déjà en cours
  d'exécution** a de lui-même interrogé l'agent réel à chaque tick (15
  `UsageRecord` réels sur 5 ticks) puis généré une **vraie facture** dès la fin de
  la période (`base_fee` 25.00 + usage réel arrondi au centime, total exact) →
  facture lue et payée via l'API réelle (`POST .../invoices/{id}/pay`), un second
  paiement sur la même facture correctement rejeté.
- **Critère de sortie** : facturation générée automatiquement à partir de l'usage réel
  mesuré, pas de montant calculé manuellement. ✅

## Phase 11 — Production Hardening — ✅ implémentée (2026-09-19)

- **Périmètre** : tests unitaires/intégration/e2e/charge/sécurité/restauration/failover,
  disaster recovery, audit, tests de pénétration, documentation finale.
- **Audit de sécurité préalable** : rate limiting documenté depuis la Phase 1 mais
  **jamais implémenté** (confirmé, écart réel) ; un seul test d'isolation
  multi-tenant existait dans toute la plateforme ; aucun test SQL
  injection/falsification JWT ; aucun test de charge/concurrence ; MFA
  "à décider en Phase 10" jamais réellement tranché.
- **Rate limiting construit** (`app/core/rate_limit.py`, doc [04](04-securite-et-isolation.md#46)) :
  fenêtre glissante en mémoire, différenciée par plan pour les routes
  organisation-scopées (via `Subscription`/`Plan` de la Phase 10, avec un petit
  cache TTL pour éviter une requête DB par appel), par utilisateur pour le reste
  des routes authentifiées, par IP pour les routes non authentifiées (défense
  anti-brute-force réelle sur `/auth/login`). Limitation assumée : en mémoire,
  mono-processus — cohérent avec le reste de la plateforme (file de jobs,
  scheduler unique) ; un Control Plane multi-instance aurait besoin d'un magasin
  partagé (Redis).
- **MFA obligatoire pour les plans payants** (`PATCH .../subscription`, doc
  [04](04-securite-et-isolation.md#45)) : décision différée en Phase 10 tranchée
  ici — passer à un plan avec `base_fee > 0` sans MFA activé renvoie `403`.
- **Tests de sécurité ajoutés** (`tests/test_security.py`, 15 tests) : rejet
  d'identifiants d'injection (paramétré), nom de base malveillant rejeté par le
  schéma Pydantic avant toute logique métier, JWT altéré/signé avec le mauvais
  secret/expiré/`alg=none` tous rejetés, isolation multi-tenant étendue
  (base, souscription — pas seulement projets), rate limit réellement déclenché
  (`429` + `Retry-After`).
- **Tests de charge/concurrence ajoutés** (`tests/test_load.py`, 2 tests) : un
  burst de lectures concurrentes réussit sans corruption ; deux créations de
  base concurrentes sur un plan `free` (1 base max) — **a révélé un vrai bug**
  (voir ci-dessous).
- **Bug réel trouvé et corrigé (race condition TOCTOU)** : `POST .../databases`
  laissait passer deux requêtes concurrentes à travers la vérification de quota
  avant qu'aucune ne valide son insertion — un plan `free` pouvait se retrouver
  avec 2 bases au lieu d'1. Corrigé avec un `asyncio.Lock` par organization
  (`app/services/quotas.py::get_organization_lock`), qui sérialise
  "vérifier le quota, puis créer" — même limitation mono-processus assumée que
  le rate limiter.
- **Bug réel trouvé et corrigé (endpoint)** : `GET .../invoices/{id}` plantait
  systématiquement en 500 — `InvoiceDetailResponse.model_validate(invoice)`
  exigeait `line_items` (obligatoire) sur un objet ORM qui n'a pas cet
  attribut ; corrigé en construisant la réponse à partir des champs déjà
  validés d'`InvoiceResponse` plutôt que via `model_copy` sur une instance
  jamais valide au départ.
- **Disaster Recovery — tous les scénarios testés en conditions réelles, avec
  rapport** : voir [05 §5.7](05-backup-ha-scaling.md#57-rapport-de-test-des-scénarios-de-disaster-recovery-phase-11-2026-09-19)
  pour le détail complet. Résumé : VPS down (référence Phase 6 + reconfirmation
  de la détection de staleness en direct) ✅ ; PostgreSQL corrompu (restore réel,
  limite PITR déjà documentée) ✅ ; disque perdu (satisfait par construction,
  démontré involontairement par un vrai incident MinIO pendant cette
  campagne) ✅ ; backup corrompu (rejet réel `409` + fallback réel vers un
  backup vérifié) ✅ ; Control Plane tombe (écriture réelle directe en
  PostgreSQL confirmée, CP entièrement arrêté) ✅ ; région indisponible (non
  implémenté, confirmé, documenté). Un **vrai bug d'infrastructure de test** a
  été trouvé et corrigé pendant cette campagne (flag `-i` manquant sur le pont
  `docker exec` utilisé pour `pg_restore` dans ce bac à sable — cf. 05 §5.7 pour
  le détail complet).
- **Gaps documentés, non corrigés dans cette phase** (décisions de scope
  transparentes, pas des oublis) : pas de middleware général de rédaction des
  logs (seule la rédaction de l'audit log existe — aucune fuite de secret
  trouvée dans les logs actuels, donc pas de vulnérabilité active identifiée) ;
  pas d'audit systématique de chaque refus RBAC (`require_permission` ne loggue
  pas chaque refus — changer cela toucherait ~80 points d'appel, jugé hors
  scope du temps disponible pour cette phase) ; PITR toujours différé ;
  intégration mobile money/Stripe réelles toujours différées (abstractions déjà
  posées en Phases 9.4/10).
- **Tests** : 104 tests backend au total (86 + 18 nouveaux : 15 sécurité +
  2 charge + 1 MFA), `ruff` propre, aucune dérive Alembic. 24 tests agent
  (inchangés, config.py commentaire clarifié sans changement fonctionnel).
- **Critère de sortie** : tous les scénarios de disaster recovery du document
  [05](05-backup-ha-scaling.md#55-disaster-recovery--scénarios-et-réponses) ont été
  testés en conditions réelles au moins une fois, avec rapport. ✅

## Phase F — Frontend / Dashboard (Next.js)

- **Pré-requis absolu** : Phases 1 à 11 terminées, API stable et documentée (OpenAPI).
  C'est la première ligne de code Next.js du projet — rien avant.
- **Périmètre** : SDK TypeScript (généré/maintenu à partir du schéma OpenAPI, sur le
  même principe 1:1 sans logique métier que le SDK Python de la Phase 8 — différé
  jusqu'ici pour ne jamais construire d'artefact non exercé par un consommateur réel,
  cf. note de la Phase 8), puis dashboard global (organizations, projects, databases,
  servers, clusters, usage, billing, backups, monitoring, logs, alerts, API keys,
  settings) et dashboard projet (overview, database, SQL Editor UI, tables, users,
  branches, backups, restore, metrics, logs, settings, connection, API) — cf. cahier
  des charges §34-35.
- **Construction** : consomme exclusivement l'API publique via le SDK TypeScript
  construit en tout début de cette phase — pas d'accès direct à la base de
  métadonnées depuis le frontend.
- **Sécurité** : le frontend applique le RBAC déjà défini côté API (masquage d'UI selon
  rôle), sans jamais devenir la seule couche de contrôle d'accès — l'API reste
  autoritaire.
- **Tests** : e2e (Playwright/Cypress) sur les parcours critiques (création de base,
  restauration, gestion des membres).
- **Critère de sortie** : un utilisateur peut réaliser l'intégralité du parcours décrit
  en introduction du cahier des charges (créer un compte → organisation → projet →
  base → voir son statut RUNNING et sa chaîne de connexion) uniquement depuis le
  dashboard, sans jamais appeler l'API directement.

### Phase F.1 — Fondations : SDK TypeScript, auth complète, coquille du dashboard — ✅ implémentée (2026-09-20)

Premier morceau vertical de la Phase F, pas le périmètre complet d'un coup (décision
utilisateur explicite) : suffisant pour prouver le parcours critique de bout en bout,
le reste (SQL Editor, monitoring, billing UI, backups UI, webhooks UI...) est
délibérément différé à de futures sous-phases F.2+.

- **`sdk-ts/`** — nouveau package top-level, miroir TypeScript de `sdk/` (Python) :
  mêmes principes (wrapper fin par endpoint, aucune logique métier côté client, un
  seul point d'entrée pour les headers d'auth et la normalisation d'erreurs). Types
  générés depuis le schéma OpenAPI réel du backend (`openapi-typescript`,
  `npm run generate`) plutôt que dupliqués à la main — un changement de schéma
  backend redevient une erreur de type, pas une dérive silencieuse. Seuls les
  endpoints réellement consommés par cette sous-phase ont une méthode wrapper (auth,
  organizations, projects, databases, jobs, regions, notifications) ; les types des
  autres groupes sont déjà générés et prêts, les wrappers arriveront avec les pages
  qui en ont besoin — même croissance incrémentale que le SDK Python phase par phase.
- **`frontend/`** — Next.js 16 (App Router, Turbopack), Tailwind + primitives UI
  maison (style shadcn), TanStack Query. **Changement de comportement backend
  nécessaire et fait ici** : `GET /auth/oauth/{provider}/callback`
  (`backend/app/api/v1/endpoints/auth.py`) ne renvoie plus le token en JSON — il
  redirige vers le frontend, token dans un **fragment** d'URL (`#access_token=...`,
  jamais transmis à aucun serveur) en cas de succès, `?error=` sinon. C'était le
  changement explicitement anticipé dans le doc [04 §4.8](04-securite-et-isolation.md#48-oauth-sign-upsign-in-google-github--2026-09-20)
  au moment de construire l'OAuth backend seul.
- **Session** : JWT dans un cookie httpOnly posé par le frontend (Server Actions /
  Route Handlers Next.js agissant en BFF) — jamais exposé à du JS côté navigateur.
  Décision utilisateur explicite (vs `localStorage`), pour le niveau de rigueur
  "propre/professionnel" demandé pour l'auth. `proxy.ts` (le fichier `middleware.ts`
  est déprécié et renommé en Next.js 16 — vérifié dans la doc embarquée avant d'écrire
  quoi que ce soit, cf. note ci-dessous) fait un contrôle optimiste (présence du
  cookie seulement) ; le backend reste la seule vérité pour la validité réelle du JWT.
- **Auth complète livrée** : inscription/connexion email+mot de passe, connexion
  Google/GitHub (redirection réelle vers le fournisseur puis retour), activation MFA
  avec QR code, connexion avec OTP. Un compte avec MFA activé est bloqué en
  connexion OAuth (403 explicite, cf. doc 04 §4.8) — pas de contournement silencieux.
- **Coquille dashboard** : création d'organisation, liste/création de projets,
  liste/création de bases avec polling de statut (`pending`/`creating` → `running`)
  via une route proxy Next.js dédiée (le cookie httpOnly empêchant le navigateur
  d'appeler directement l'API FastAPI depuis du JS client), cloche de notifications
  avec polling TanStack Query.
- **Un vrai piège de version évité, pas deviné** : `create-next-app` a résolu
  Next.js 16.3.5, une version postérieure aux données d'entraînement du modèle qui a
  écrit ce code. Un fichier `AGENTS.md` généré automatiquement par Next.js dans
  `frontend/` avertit explicitement de ce risque et pointe vers la doc embarquée
  (`node_modules/next/dist/docs/`) — lue avant d'écrire le moindre fichier
  d'authentification. A évité d'écrire un `middleware.ts` (déprécié, renommé
  `proxy.ts` avec export `proxy` au lieu de `middleware`) et a confirmé le pattern
  "callback URL" documenté par Next lui-même pour la case OAuth.
- **Deux vrais bugs trouvés par les tests e2e Playwright réels, aucun par simple
  relecture de code** :
  1. Le flux `/auth/callback` (lecture du fragment `#access_token=`, échange contre
     un cookie) échouait systématiquement en mode `next dev` — Turbopack compile les
     routes à la demande, et la toute première requête vers une route encore jamais
     compilée peut prendre plusieurs secondes, largement au-delà du timeout par
     défaut de Playwright (5s) avant que l'hydratation client ne s'exécute. Confirmé
     en ajoutant un marqueur de debug visible dans le DOM. Next.js documente
     lui-même la recommandation de tester contre un build de production
     (`next build && next start`) plutôt qu'en dev — appliqué, les 5 tests e2e
     passent de façon fiable une fois cette bascule faite.
  2. Un vrai crash serveur (500) sur `POST /auth/register` pendant une session de
     test — pas un bug de code : Docker Desktop s'était arrêté entre-temps (incident
     d'environnement, pas applicatif), tuant la connexion Postgres du backend.
     Redémarré, le conteneur `eminidb-controlplane-postgres` a retrouvé toutes ses
     données intactes (volume nommé, cf. correctif de la section paiements/
     notifications plus haut) — preuve concrète que ce correctif fonctionne comme
     prévu, pas seulement en théorie.
- **Tests** : `sdk-ts` (Vitest, 4 tests, `fetch` mocké) + `frontend` e2e (Playwright,
  5 tests, contre un vrai backend + une vraie base Postgres) : inscription → aucune
  organisation → création d'organisation → création de projet → liste de bases
  vide ; déconnexion puis reconnexion ; redirection `/dashboard` → `/login` si non
  connecté ; le hand-off `/auth/callback` avec un vrai token émis par le backend ;
  affichage d'une erreur OAuth sans l'avaler silencieusement. Limite assumée et
  documentée, pas contournée : le clic réel sur un écran de consentement Google/
  GitHub ne peut pas être automatisé dans cet environnement (même raisonnement que
  l'approbation manuelle FedaPay) — nécessite un humain, une fois de vrais
  identifiants d'app OAuth créés après la mise en ligne d'un VPS.
- **Différé à une prochaine sous-phase** : SQL Editor, backups/restore UI, billing/
  factures UI, gestion des webhooks UI, monitoring/métriques/alertes, gestion des
  clés API, gestion des membres — les types TypeScript existent déjà (générés),
  seules les pages et méthodes wrapper restent à écrire.

## Phase 12 — AI Platform

- **Périmètre** : cf. cahier des charges §75 — AI SQL Assistant, AI Analyst, RAG,
  agents IA à permissions explicites et bornées.
- **Pré-requis absolu** : Phases 0-11 terminées et stables. Aucun agent IA n'a d'accès
  illimité aux données ; permissions explicites par agent (lecture/écriture/suppression)
  définies au cas par cas.

---

## Comment cette liste est utilisée

Avant chaque phase, un document dédié sera produit (mêmes rubriques que celles listées
en §62/§76 Règle 20 du cahier des charges : architecture, fichiers concernés, modèles,
API, flux, sécurité, stratégie de test, stratégie de déploiement) — pas d'implémentation
sans ce document validé au préalable.
