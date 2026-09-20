"""Staff RBAC permission matrix (cf. docs/architecture/08 §8.9) — distinct from
the Control Plane's own org RBAC (backend/app/services/rbac.py): these are
business roles scoped to an institution, never to a cloud project."""

from __future__ import annotations

from fastapi import HTTPException, status

from mf_app.models.staff_user import MFStaffRole as R

_ALL_ROLES = {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.LOAN_OFFICER, R.TELLER}

_PERMISSIONS: dict[str, set[R]] = {
    "branches:manage": {R.INSTITUTION_ADMIN},
    "branches:read": _ALL_ROLES,
    "staff:manage": {R.INSTITUTION_ADMIN},
    "staff:read": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER},
    "customers:manage": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.LOAN_OFFICER},
    "customers:read": _ALL_ROLES,
    "savings_products:manage": {R.INSTITUTION_ADMIN},
    "savings_products:read": _ALL_ROLES,
    # Cash-handling operations (open account, deposit, withdraw) — tellers do
    # this in real branch operations, loan officers do not.
    "savings:transact": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.TELLER},
    "savings:read": _ALL_ROLES,
    "loan_products:manage": {R.INSTITUTION_ADMIN},
    "loan_products:read": _ALL_ROLES,
    # Preparing/submitting a loan application — loan officers do this.
    "loans:manage": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.LOAN_OFFICER},
    # Segregation of duties: whoever prepares a loan file should not also be
    # the one who approves it — tellers don't approve credit either.
    "loans:approve": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER},
    # Cash-handling, same tier as savings:transact.
    "loans:disburse": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.TELLER},
    "loans:repay": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER, R.TELLER},
    "loans:read": _ALL_ROLES,
    # Financial reports are more sensitive than day-to-day operational data —
    # restricted to management, unlike branches:read/savings:read/loans:read.
    "reports:read": {R.INSTITUTION_ADMIN, R.BRANCH_MANAGER},
}


def has_permission(role: R, action: str) -> bool:
    allowed = _PERMISSIONS.get(action)
    if allowed is None:
        raise ValueError(f"Unknown RBAC action: {action}")
    return role in allowed


def require_permission(role: R, action: str) -> None:
    if not has_permission(role, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role.value}' is not allowed to perform '{action}'",
        )
