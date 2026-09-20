from fastapi import APIRouter

from app.api.v1.endpoints import (
    api_keys,
    auth,
    billing,
    clusters,
    database_admin,
    database_backups,
    database_ops,
    database_roles,
    database_sql,
    databases,
    jobs,
    nodes,
    notifications,
    organizations,
    payment_webhooks,
    projects,
    regions,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(projects.router)
api_router.include_router(api_keys.router)
api_router.include_router(webhooks.router)
api_router.include_router(regions.router)
api_router.include_router(nodes.router)
api_router.include_router(clusters.router)
api_router.include_router(databases.router)
api_router.include_router(database_roles.router)
api_router.include_router(database_sql.router)
api_router.include_router(database_ops.router)
api_router.include_router(database_backups.router)
api_router.include_router(database_admin.router)
api_router.include_router(jobs.router)
api_router.include_router(billing.plans_router)
api_router.include_router(billing.router)
api_router.include_router(payment_webhooks.router)
api_router.include_router(notifications.router)
