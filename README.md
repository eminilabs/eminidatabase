# eminidatabase — Cloud Database Platform

Plateforme Cloud Database / DBaaS propriétaire : provisioning automatique de bases
PostgreSQL, gestion multi-tenant, backups, PITR, réplication, haute disponibilité,
scaling, monitoring — avec, au-dessus, un module métier microfinance, et à terme une
couche IA.

**Stack** : FastAPI (backend) + Next.js (frontend). Le backend est développé et
stabilisé dans son intégralité avant que le moindre travail frontend ne démarre — voir
la règle de séquencement dans
[docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md).

## Documentation d'architecture

Voir [docs/architecture/00-README.md](docs/architecture/00-README.md) pour :
- l'architecture globale (Control Plane vs Data Plane) ;
- le modèle de données du Control Plane ;
- le Database Orchestrator et le Data Plane Agent ;
- le modèle de sécurité et d'isolation multi-tenant ;
- backup / PITR / haute disponibilité / scaling / disaster recovery ;
- le réseau et la stratégie de déploiement ;
- l'API, la CLI et les SDKs ;
- le positionnement du module microfinance et du billing ;
- le plan de phases (0 à 12) avec critères de sortie.

## Composants

- [backend/](backend/README.md) — Control Plane (FastAPI) : auth, organizations,
  RBAC, projects, nodes/regions, CA interne.
- [agent/](agent/README.md) — Data Plane Agent : tourne sur chaque node, enregistrement
  mTLS auprès du Control Plane, heartbeat, health/resources.
- [sdk/](sdk/README.md) — SDK Python officiel et CLI (`platform`) pour un
  développeur tiers, construits entièrement au-dessus de l'API publique.
- [microfinance/](microfinance/README.md) — application métier microfinance,
  elle-même **cliente** de la plateforme (dogfooding du SDK) plutôt qu'un
  composant de celle-ci.

## Statut

- Phase 0 (architecture) : rédigée.
- Phase 1 (Control Plane — auth, organizations, memberships/RBAC, projects, API keys,
  audit log) : implémentée et testée.
- Phase 2 (Data Plane — Data Plane Agent, CA interne, enregistrement/heartbeat des
  nodes, mTLS Control Plane ↔ Agent) : implémentée et testée, vérifiée de bout en
  bout avec un vrai handshake mTLS.
- Phase 3 (Database Orchestrator — placement, provisioning réel d'une base
  PostgreSQL, credentials chiffrés, lifecycle create/suspend/resume/delete, jobs
  asynchrones) : implémentée et testée, vérifiée de bout en bout avec un vrai
  PostgreSQL (Docker) : création d'une base par API, connexion réelle avec les
  credentials renvoyés, suspend/resume/delete tous confirmés au niveau PostgreSQL
  lui-même.
- Phase 4 (Database Management — rôles PostgreSQL additionnels, extensions en liste
  blanche, SQL Editor sécurisé, introspection de schéma, métriques) : implémentée et
  testée, vérifiée de bout en bout avec un vrai PostgreSQL — SQL réel exécuté sous
  l'identité du rôle Postgres choisi, rôle `readonly` bloqué par PostgreSQL sur un
  `INSERT` comme attendu, extension installée/vérifiée, rôle supprimé et confirmé
  absent de PostgreSQL.
- Phase 5 (Backup et Recovery — backups logiques auto/manuels vers un object storage
  S3-compatible, restore vers une nouvelle base, vérification périodique en tâche de
  fond, rétention) : implémentée et testée (73 tests au total : 55 backend + 18
  agent, dont de vrais tests d'intégration `pg_dump`/`pg_restore`/MinIO qui ont
  trouvé et fait corriger un bug réel — les objets restaurés appartenaient à l'admin
  au lieu du tenant, causant un *"permission denied"* pour le client sur ses propres
  données). **Vérifiée de bout en bout** avec un vrai PostgreSQL et un vrai MinIO :
  backup réel confirmé présent dans le stockage objet, restauration avec données
  intactes et accessibles en écriture sous l'identité du tenant, vérification
  automatique déclenchée par un planificateur en tâche de fond distinct du worker —
  voir [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  (y compris la note sur le PITR, explicitement différé à la Phase 6 avec la
  réplication plutôt que construit à moitié).
  Aucun frontend — tout se teste via Swagger UI (`/docs`) ou curl/httpie.
- Phase 6 (Haute disponibilité — réplication PostgreSQL en streaming, health
  monitoring, failover automatique/manuel) : implémentée et testée (83 tests au
  total : 62 backend + 21 agent). **Vérifiée de bout en bout avec deux vrais
  PostgreSQL en réplication en streaming réelle** (Docker) : replica attaché via
  l'API après vérification réelle de son statut, primary réellement arrêté, vraie
  promotion PostgreSQL (`pg_promote()`) déclenchée par l'API, base de données
  repointée automatiquement vers le node promu, données antérieures intactes et
  nouvelle écriture réussie sur le nouveau primary. Voir
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  pour le détail (y compris la frontière assumée entre provisioning d'un replica —
  traité comme une étape infra "jour 0" — et les opérations de haute disponibilité
  proprement dites, qui sont du vrai code de plateforme testé).
  Aucun frontend — tout se teste via Swagger UI (`/docs`) ou curl/httpie.
- Phase 7 (Scaling — resize vertical, migration réelle d'une base entre nodes) :
  implémentée et testée (96 tests au total : 72 backend + 24 agent). **Vérifiée de
  bout en bout avec trois vrais PostgreSQL** : resize confirmé au niveau PostgreSQL
  réel (`datconnlimit`), migration round-trip réelle entre deux nodes indépendants
  avec données intactes et écriture réussie après coup, source physiquement
  supprimée seulement après confirmation du succès de la cible. Cette phase a mis
  au jour et corrigé **trois bugs réels en cascade** sur le même mécanisme de
  "quiescence" avant sauvegarde (voir le détail dans
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md))
  — exactement le genre de subtilité PostgreSQL qu'une suite entièrement mockée
  n'aurait jamais révélée.
  Aucun frontend — tout se teste via Swagger UI (`/docs`) ou curl/httpie.
- Phase 8 (Developer Platform — SDK Python officiel, CLI `platform` construite
  dessus, webhooks signés HMAC) : implémentée et testée (109 tests au total : 79
  backend + 24 agent + 10 SDK/CLI). **Vérifiée de bout en bout entièrement via la
  CLI, sans dashboard** : création de compte/organisation/projet/base, connexion,
  exécution SQL réelle, resize, backup (`--wait`), gestion de webhooks — et
  livraison réelle d'un webhook prouvée séparément (vrai socket HTTP local, vraie
  signature HMAC-SHA256, `WebhookDelivery.status = SUCCEEDED`). SDKs
  TypeScript/Go différés à la Phase F (cf.
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  pour le raisonnement). Voir [sdk/README.md](sdk/README.md).
- **Phase 9 (Microfinance) — ✅ implémentée en entier** (9.1 Fondations, 9.2
  Ledger et épargne, 9.3 Crédit, 9.4 Comptabilité et paiements) : nouveau
  déployable `microfinance/`, **client** de la plateforme (dogfooding réel du
  SDK Python de la Phase 8) plutôt que composant de celle-ci — une organization
  CP unique pour le produit microfinance, un project/database par institution.
  Moteur de ledger double-écriture générique (comptes internes, épargne, prêts),
  cycle de crédit complet (demande → soumission → approbation → décaissement →
  échéancier déterministe → remboursement → clôture automatique — le critère de
  sortie explicite de la Phase 9), rapport de balance générale comme preuve
  d'audit, couche d'abstraction de paiement (intégration mobile money réelle
  différée). 138 tests au total sur toute la plateforme désormais (79 backend +
  24 agent + 10 SDK/CLI + 29 microfinance, ces derniers embarquant le **vrai**
  backend en process pour prouver le dogfooding automatiquement). **Vérifiée de
  bout en bout avec un vrai backend, un vrai agent (mTLS réel) et un vrai
  PostgreSQL** : onboarding réel d'une institution → cycle de crédit complet
  réellement décaissé/remboursé/clôturé → balance générale réellement équilibrée
  (140,13 = 140,13) après une activité mêlant épargne et crédit — tout confirmé
  par lecture directe dans PostgreSQL, pas seulement via l'API. Voir
  [microfinance/README.md](microfinance/README.md) et
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  pour le détail (dont plusieurs bugs réels trouvés et corrigés — piège
  tzinfo/SQLite, course de concurrence entre deux transactions SQLite partageant
  une connexion, paramètre mort dans l'ouverture d'un compte d'épargne).
- **Phase 10 (Billing et SaaS) — ✅ implémentée** : contrairement à la Phase 9, ceci
  vit **dans `backend/`** (la plateforme se facture elle-même, pas un nouveau
  déployable) — plans/quotas configurables en base, souscription `free`
  automatique à la création d'une organization, quotas réellement appliqués au
  provisioning (`402 Payment Required` en cas de dépassement), usage mesuré
  réellement à chaque tick du scheduler (vrais appels agent, jamais de valeur
  inventée), génération automatique de factures agrégées et arrondies au
  centime, paiement via une couche d'abstraction (intégration Stripe réelle
  différée). 86 tests backend (+7), aucune régression. **Vérifiée de bout en
  bout avec le vrai scheduler tournant en tâche de fond, sans aucun appel de
  fonction manuel** : deuxième base réellement rejetée par quota, 15
  `UsageRecord` réels générés sur 5 ticks contre un vrai agent, facture réelle
  générée automatiquement à l'échéance (base_fee + usage, total exact),
  facture payée via l'API réelle. Voir
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  pour le détail complet, dont 6 bugs réels trouvés et corrigés (1 dans le
  produit, 5 dans les tests).
- **Phase 11 (Production Hardening) — ✅ implémentée** : rate limiting construit
  (documenté depuis la Phase 1, jamais implémenté avant — fenêtre glissante en
  mémoire, différenciée par plan via Phase 10, défense anti-brute-force réelle
  sur `/auth/login`) ; MFA rendue obligatoire pour upgrader vers un plan payant
  (décision différée en Phase 10, tranchée ici) ; 18 nouveaux tests
  sécurité/charge (104 tests backend au total) — dont un test de concurrence qui
  a **révélé un vrai bug** (race condition TOCTOU sur la vérification de quota,
  corrigée avec un verrou par organization) et un test e2e qui a révélé un
  second bug produit (`GET .../invoices/{id}` plantait en 500). **Tous les
  scénarios de disaster recovery du document 05 testés en conditions réelles,
  avec rapport** — dont un vrai incident survenu pendant la campagne (crash de
  Docker Desktop ayant réellement fait perdre son volume à MinIO, PostgreSQL
  ayant lui survécu intact) qui a permis de trouver et corriger un vrai bug
  d'infrastructure de test (flag `-i` manquant sur le pont `docker exec` de
  `pg_restore`). Voir
  [docs/architecture/09-plan-de-phases.md](docs/architecture/09-plan-de-phases.md)
  et [05 §5.7](docs/architecture/05-backup-ha-scaling.md#57-rapport-de-test-des-scénarios-de-disaster-recovery-phase-11-2026-09-19)
  pour le rapport complet.
- Prochaine étape : Phase F (Frontend/Dashboard) ou Phase 12 (IA), selon la
  priorité du porteur de projet — l'intégralité du backend (Phases 1-11) est
  désormais implémentée, testée et durcie. Le PITR (archivage WAL continu,
  différé depuis la Phase 5), la récupération en libre-service d'une base
  `FAILED` (gap identifié en Phase 7), l'intégration mobile money/Stripe réelles
  (abstractions posées en Phases 9.4/10) et l'audit systématique de chaque refus
  RBAC (gap identifié en Phase 11) restent des pistes ouvertes documentées, pas
  oubliées.
