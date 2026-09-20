# 07 — API, CLI, SDK

## 7.1 Surface API (v1)

Toutes les routes sont versionnées (`/api/v1/...`), documentées en OpenAPI (généré
automatiquement par FastAPI), protégées par auth (session ou API key) + RBAC + audit.

```
# Auth
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/mfa/verify
POST   /api/v1/auth/logout
POST   /api/v1/auth/api-keys
DELETE /api/v1/auth/api-keys/{id}

# Organizations
GET    /api/v1/organizations
POST   /api/v1/organizations
GET    /api/v1/organizations/{id}
POST   /api/v1/organizations/{id}/members
DELETE /api/v1/organizations/{id}/members/{user_id}

# Projects
GET    /api/v1/organizations/{org_id}/projects
POST   /api/v1/organizations/{org_id}/projects
GET    /api/v1/projects/{id}

# Databases
POST   /api/v1/projects/{id}/databases
GET    /api/v1/projects/{id}/databases
GET    /api/v1/databases/{id}
POST   /api/v1/databases/{id}/resize
POST   /api/v1/databases/{id}/suspend
POST   /api/v1/databases/{id}/resume
DELETE /api/v1/databases/{id}
GET    /api/v1/databases/{id}/connection
POST   /api/v1/databases/{id}/credentials/rotate

# Branching (Phase 7+)
POST   /api/v1/databases/{id}/branches
GET    /api/v1/databases/{id}/branches
POST   /api/v1/branches/{id}/promote
DELETE /api/v1/branches/{id}

# Backups
POST   /api/v1/databases/{id}/backups
GET    /api/v1/databases/{id}/backups
POST   /api/v1/backups/{id}/restore
GET    /api/v1/backups/{id}/verification

# Nodes / Clusters / Regions (admin plateforme)
GET    /api/v1/regions
GET    /api/v1/nodes
POST   /api/v1/nodes/register
GET    /api/v1/clusters/{id}

# Monitoring / Logs
GET    /api/v1/databases/{id}/metrics
GET    /api/v1/databases/{id}/logs

# Billing / Usage
GET    /api/v1/organizations/{id}/usage
GET    /api/v1/organizations/{id}/invoices
GET    /api/v1/plans

# Audit
GET    /api/v1/organizations/{id}/audit-logs

# Jobs (suivi des opérations asynchrones)
GET    /api/v1/jobs/{id}
```

Principes transverses :
- Idempotence via header `Idempotency-Key` sur tous les POST de création/mutation
  critique.
- Pagination systématique sur les listes (`limit`/`cursor`).
- Rate limiting par API key, avec en-têtes `X-RateLimit-*`.
- Réponses d'erreur normalisées (`{code, message, details}`), jamais de stack trace
  exposée au client.

## 7.2 CLI

```bash
platform login
platform organizations list
platform projects create my-project
platform db create production --project my-project --region eu-west --cpu 2 --ram 4096 --storage 50
platform db list --project my-project
platform db connect production
platform db backup create production
platform db backup list production
platform db restore production --backup <id> --at "2026-09-01T10:00:00Z"
platform db branch create staging --from production
platform db resize production --cpu 4 --ram 8192
platform db logs production --follow
```

- Implémentée en Python (Typer/Click) au-dessus du SDK Python — pas de logique
  dupliquée entre CLI et SDK.
- Authentification via token stocké localement (comparable à `~/.platform/credentials`),
  jamais le mot de passe en clair.

## 7.3 SDKs

| Langage | Statut | Notes |
|---|---|---|
| TypeScript/JavaScript | Phase 8 | généré/maintenu en parallèle du dashboard Next.js, réutilisation des types |
| Python | Phase 8 | miroir direct de l'API, utilisé aussi par la CLI |
| Go | Phase 8+ | ajouté si la demande utilisateur le justifie |

Architecture commune : un client HTTP mince généré (ou semi-généré) à partir du schéma
OpenAPI, pour éviter la dérive entre l'API réelle et les SDKs.

## 7.4 Webhooks (Phase 8)

Événements exposés : `database.created`, `database.running`, `database.failed`,
`backup.completed`, `backup.failed`, `restore.completed`. Signature HMAC des payloads,
retries avec backoff, journal de livraison consultable par le client.
