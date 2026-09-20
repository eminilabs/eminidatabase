# 04 — Sécurité et isolation multi-tenant

## 4.1 Modèle multi-tenant

```
Platform
 ├── Organization (tenant) A
 │    ├── Membership (user ↔ role)
 │    └── Project A1 → Databases
 └── Organization (tenant) B
      └── Project B1 → Databases
```

`organization_id` est la frontière de tenant. Elle est propagée et vérifiée à chaque
couche :

| Couche | Mécanisme d'isolation |
|---|---|
| API | Chaque requête authentifiée résout un `organization_id` (via JWT ou API key) ; tout filtre de requête l'inclut systématiquement — pas de requête "globale" sans scope explicite admin |
| RBAC | Rôles : `owner`, `admin`, `developer`, `billing`, `readonly`, scopés à l'organisation ou au projet |
| Base de métadonnées | Row-level filtering applicatif obligatoire (et Postgres RLS en défense en profondeur sur les tables sensibles) |
| PostgreSQL client | Un rôle applicatif par base, jamais de rôle superuser partagé entre tenants |
| Réseau | Un client ne peut atteindre que l'endpoint (host:port) de ses propres bases ; pas de réseau plat entre bases de tenants différents sur un même node |
| Stockage | Répertoires de données séparés par base ; backups préfixés par `organization_id/project_id/database_id` dans l'object storage |
| Credentials | Un secret par base, jamais réutilisé entre tenants |
| Logs | Filtrage par `organization_id` avant tout affichage dans le dashboard |
| Backups | Restauration croisée entre tenants explicitement interdite au niveau API (vérification `organization_id` source == destination, sauf opération admin auditée) |

## 4.2 RBAC — rôles de plateforme

| Rôle | Portée | Peut |
|---|---|---|
| `owner` | Organization | tout, y compris supprimer l'organisation, gérer billing |
| `admin` | Organization | gérer projets, membres, bases — pas billing/suppression org |
| `developer` | Project | créer/gérer des bases dans les projets autorisés |
| `billing` | Organization | lecture usage/factures uniquement |
| `readonly` | Project | lecture seule (dashboard, métriques) |

Les permissions sont vérifiées côté API pour **chaque** endpoint (middleware
centralisé, pas de vérification ad hoc dispersée dans le code métier), et chaque refus
est audité.

## 4.3 Stratégies d'isolation infrastructure

Conforme au cahier des charges §13, le niveau est piloté par le plan/besoin, pas figé :

- **Partagé** : plusieurs `DATABASES` sur un même `CLUSTER`/node — plans Free/Developer/Pro.
- **Dédié** : un `CLUSTER` avec une seule `DATABASE` — plans Business/Enterprise.
- **Cluster HA** : primary + replicas dédiés — Enterprise / exigences de disponibilité.

La table `DATABASES.isolation_level` et le placement de l'Orchestrator (cf.
[03](03-database-orchestrator-et-agent.md)) implémentent ce choix — jamais une
décision figée dans le code.

## 4.4 Gestion des secrets

- Mots de passe PostgreSQL générés côté Data Plane Agent, jamais choisis par le client
  ni transmis en clair dans le corps d'une requête API de création.
- Stockage : secret manager dédié (Vault en cible ; en développement, chiffrement
  applicatif AES-GCM avec clé KMS/env séparée du code, jamais en base en clair).
- `DATABASE_CREDENTIALS` ne stocke qu'une référence (`secret_ref`), jamais le secret.
- Rotation : endpoint explicite `POST /databases/{id}/credentials/rotate`, opération
  auditée et à double confirmation pour les rôles admin.
- **Aucun secret dans les logs** — middleware de logging avec redaction automatique des
  champs connus (`password`, `secret`, `token`, `connection_string`) avant écriture.

## 4.5 Opérations administratives à haut risque

Liste (cahier des charges §57) nécessitant confirmation renforcée :
suppression de base/cluster/tenant, restauration, changement de permissions, rotation
de secrets, modification de ressources en production.

Mécanisme commun :
1. Confirmation explicite côté client (re-saisie du nom de la ressource).
2. Vérification de permission stricte (souvent `owner` uniquement).
3. Audit log systématique avant/après (`before`/`after` dans `AUDIT_LOGS`).
4. Pour la suppression : `deleted_at` soft-delete + période de rétention avant purge
   physique définitive (ex. 7 jours), sauf demande explicite de purge immédiate.
5. MFA recommandé en Phase 1 pour les rôles `owner`/`admin` sur les organisations
   payantes (activation obligatoire à définir en Phase 10 avec le billing).

## 4.6 Sécurité réseau

- Reverse proxy / API Gateway en frontière, TLS partout (Let's Encrypt via Traefik en
  développement/petite prod, certificats gérés en prod à grande échelle).
- Communication Control Plane → Data Plane Agent : mTLS uniquement, pas d'exposition
  publique de l'agent (bind sur interface privée / VPN / réseau privé de l'hébergeur
  VPS quand disponible).
- Rate limiting sur l'API publique (par API key/IP), avec limites différenciées par
  plan.
- Validation stricte de toutes les entrées (Pydantic côté FastAPI) avant toute
  utilisation dans une commande système ou SQL.

## 4.7 Audit

Toute action sensible génère une ligne `AUDIT_LOGS` (cf. [02](02-modele-donnees.md))
incluant l'acteur, l'action, la ressource, l'état avant/après, l'IP, le résultat. Le
journal d'audit est en lecture seule pour tous les rôles sauf export contrôlé.
