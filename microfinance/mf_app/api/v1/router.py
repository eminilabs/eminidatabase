from fastapi import APIRouter

from mf_app.api.v1.endpoints import (
    auth,
    branches,
    customers,
    institutions,
    jobs,
    loans,
    reports,
    savings,
    staff,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(institutions.router)
api_router.include_router(jobs.router)
api_router.include_router(auth.router)
api_router.include_router(branches.router)
api_router.include_router(staff.router)
api_router.include_router(customers.router)
api_router.include_router(savings.products_router)
api_router.include_router(savings.customer_accounts_router)
api_router.include_router(savings.accounts_router)
api_router.include_router(loans.products_router)
api_router.include_router(loans.router)
api_router.include_router(reports.router)
