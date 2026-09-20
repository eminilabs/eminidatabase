# Architecture — Cloud Database Platform

> Phase 0 — Document d'architecture, produit avant toute implémentation, conformément
> au cahier des charges maître. Aucune ligne de code métier n'est écrite tant que cette
> architecture n'est pas validée par le porteur du projet.

## Philosophie

> "Une infrastructure Cloud capable de provisionner, héberger, sécuriser, administrer,
> surveiller, sauvegarder, répliquer et faire évoluer automatiquement les bases de
> données de ses clients."

Ce n'est **pas** une application CRUD qui écrit des lignes dans une table `databases`.
Créer une base doit déclencher un vrai processus d'orchestration qui se termine par du
PostgreSQL réellement provisionné sur un nœud réel, avec des credentials réels.

## Sommaire des documents

| # | Document | Contenu |
|---|----------|---------|
| 01 | [Architecture globale](01-architecture-globale.md) | Control Plane vs Data Plane, composants, trajectoire VPS → multi-région |
| 02 | [Modèle de données](02-modele-donnees.md) | Schéma du Control Plane (métadonnées), ERD, machine à états |
| 03 | [Orchestrator & Agent](03-database-orchestrator-et-agent.md) | Database Orchestrator, Data Plane Agent, flux de provisioning, jobs |
| 04 | [Sécurité & isolation](04-securite-et-isolation.md) | RBAC, multi-tenancy, secrets, réseau, audit |
| 05 | [Backup, HA, Scaling](05-backup-ha-scaling.md) | Backups, PITR, réplication, failover, disaster recovery, scaling |
| 06 | [Réseau & déploiement](06-reseau-et-deploiement.md) | Topologie VPS, dev vs prod, Docker/K8s, régions |
| 07 | [API, CLI, SDK](07-api-cli-sdk.md) | Surface API, endpoints, CLI, SDKs |
| 08 | [Microfinance & Billing](08-microfinance-et-billing.md) | Module métier au-dessus de l'infra, billing SaaS |
| 09 | [Plan de phases](09-plan-de-phases.md) | Phases 0 → 12, livrables et critères de sortie de chaque phase |

## Règles absolues (rappel, cahier des charges §76)

1. Jamais commencer par l'IA — phase 12 uniquement.
2. Jamais dégénérer en simple CRUD SaaS.
3. Toujours distinguer Control Plane / Data Plane / Database Orchestrator / Data Plane Agent / Customer Database.
4. Une base client n'est jamais une ligne d'une table du Control Plane : c'est une ressource provisionnée sur un Data Plane.
5. Le système sait toujours : quelle base, quel projet, quel tenant, quel cluster, quel node, quelle région, quelles ressources, quel statut.
6. Aucune hypothèse "un seul VPS suffira" — le placement est décidé par l'Orchestrator.
7. Neon (ou tout Postgres managé tiers) sert uniquement de métadonnées Control Plane en développement — jamais d'infrastructure permanente pour les bases clientes.
8. Sécurité intégrée dès le premier composant, pas ajoutée après coup.
9. Opérations longues → jobs asynchrones, idempotents quand c'est requis.
10. Une fonctionnalité n'est terminée que si : Implémentée + Testée + Sécurisée + Documentée + Monitorée.

## Statut

**En attente de validation.** Aucune implémentation ne démarre avant retour explicite
sur cette architecture (cf. document 09, Phase 0 → critère de sortie).
