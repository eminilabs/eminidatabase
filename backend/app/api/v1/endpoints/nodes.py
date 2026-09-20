from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_authenticated_node, require_platform_admin
from app.core.security import (
    generate_bootstrap_token,
    generate_node_secret,
    verify_bootstrap_token,
)
from app.core.timeutil import as_aware_utc, utcnow
from app.db.session import get_db
from app.models.node import Node
from app.models.node_registration_token import NodeRegistrationToken
from app.models.region import Region
from app.models.user import User
from app.schemas.node import (
    NodeHealthCheckResult,
    NodeHeartbeatRequest,
    NodeRegisterRequest,
    NodeRegisterResponse,
    NodeResponse,
)
from app.schemas.node_registration_token import (
    NodeRegistrationTokenCreate,
    NodeRegistrationTokenCreated,
)
from app.services.agent_client import AgentUnreachableError, call_agent
from app.services.audit import record_audit
from app.services.ca import ca_certificate_pem, sign_node_csr
from app.services.node_health import effective_status

router = APIRouter(prefix="/nodes", tags=["nodes"])

_bootstrap_scheme = HTTPBearer(auto_error=False)


def _to_response(node: Node) -> NodeResponse:
    return NodeResponse(
        id=node.id,
        region_id=node.region_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        cpu_total=node.cpu_total,
        ram_total_mb=node.ram_total_mb,
        storage_total_gb=node.storage_total_gb,
        cpu_used=node.cpu_used,
        ram_used_mb=node.ram_used_mb,
        storage_used_gb=node.storage_used_gb,
        agent_version=node.agent_version,
        agent_port=node.agent_port,
        postgres_port=node.postgres_port,
        status=node.status.value,
        effective_status=effective_status(node),
        last_heartbeat_at=node.last_heartbeat_at,
        created_at=node.created_at,
    )


@router.post("/register", response_model=NodeRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_node(
    payload: NodeRegisterRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bootstrap_scheme),
    db: AsyncSession = Depends(get_db),
) -> NodeRegisterResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bootstrap token"
        )

    region = (
        await db.execute(
            select(Region).where(Region.code == payload.region_code, Region.active.is_(True))
        )
    ).scalar_one_or_none()
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive region"
        )

    now = utcnow()
    candidates = (
        await db.execute(
            select(NodeRegistrationToken).where(
                NodeRegistrationToken.region_id == region.id,
                NodeRegistrationToken.used_at.is_(None),
            )
        )
    ).scalars().all()

    matched_token = next(
        (
            c
            for c in candidates
            if as_aware_utc(c.expires_at) >= now
            and verify_bootstrap_token(credentials.credentials, c.token_hash)
        ),
        None,
    )
    if matched_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already-used bootstrap token",
        )
    matched_token.used_at = now

    node_secret, node_secret_hash = generate_node_secret()
    node = Node(
        region_id=region.id,
        hostname=payload.hostname,
        ip_address=payload.ip_address,
        cpu_total=payload.cpu_total,
        ram_total_mb=payload.ram_total_mb,
        storage_total_gb=payload.storage_total_gb,
        agent_version=payload.agent_version,
        agent_port=payload.agent_port,
        postgres_port=payload.postgres_port,
        node_secret_hash=node_secret_hash,
    )
    db.add(node)
    await db.flush()  # assigns node.id, needed as the certificate's CommonName

    try:
        issued = sign_node_csr(
            payload.csr_pem, common_name=str(node.id), ip_address=payload.ip_address
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid CSR: {exc}"
        ) from exc

    node.certificate_serial = issued.serial_number

    await record_audit(
        db,
        action="NODE_REGISTERED",
        resource_type="node",
        resource_id=node.id,
        after={"hostname": node.hostname, "region": region.code},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return NodeRegisterResponse(
        node_id=node.id,
        node_secret=node_secret,
        certificate_pem=issued.certificate_pem,
        ca_certificate_pem=ca_certificate_pem(),
    )


@router.post(
    "/registration-tokens",
    response_model=NodeRegistrationTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_registration_token(
    payload: NodeRegistrationTokenCreate,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> NodeRegistrationTokenCreated:
    region = (
        await db.execute(select(Region).where(Region.code == payload.region_code))
    ).scalar_one_or_none()
    if region is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown region")

    token, token_hash = generate_bootstrap_token()
    expires_at = utcnow() + dt.timedelta(minutes=payload.expires_in_minutes)
    record = NodeRegistrationToken(
        region_id=region.id, token_hash=token_hash, note=payload.note, expires_at=expires_at
    )
    db.add(record)
    await record_audit(
        db,
        action="NODE_REGISTRATION_TOKEN_CREATED",
        resource_type="node_registration_token",
        user_id=admin.id,
        after={"region": region.code, "expires_at": expires_at.isoformat()},
    )
    await db.commit()
    return NodeRegistrationTokenCreated(token=token, region_code=region.code, expires_at=expires_at)


@router.get("", response_model=list[NodeResponse])
async def list_nodes(
    _: User = Depends(require_platform_admin), db: AsyncSession = Depends(get_db)
) -> list[NodeResponse]:
    result = await db.execute(select(Node))
    return [_to_response(n) for n in result.scalars().all()]


@router.get("/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: uuid.UUID,
    _: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> NodeResponse:
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return _to_response(node)


@router.post("/{node_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def heartbeat(
    node_id: uuid.UUID,
    payload: NodeHeartbeatRequest,
    node: Node = Depends(get_authenticated_node),
    db: AsyncSession = Depends(get_db),
) -> None:
    node.last_heartbeat_at = utcnow()
    if payload.cpu_used is not None:
        node.cpu_used = payload.cpu_used
    if payload.ram_used_mb is not None:
        node.ram_used_mb = payload.ram_used_mb
    if payload.storage_used_gb is not None:
        node.storage_used_gb = payload.storage_used_gb
    if payload.agent_version is not None:
        node.agent_version = payload.agent_version
    await db.commit()


@router.post("/{node_id}/health-check", response_model=NodeHealthCheckResult)
async def health_check(
    node_id: uuid.UUID,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> NodeHealthCheckResult:
    """Manually triggers a real mTLS call from the Control Plane to the Data Plane
    Agent — the Phase 2 exit criterion ("commande déclenchée manuellement par API")."""
    node = await db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    try:
        resp = await call_agent(node, "GET", "/v1/health", timeout=5.0)
        detail = resp.text
        reachable = True
    except AgentUnreachableError as exc:
        reachable = False
        detail = str(exc)

    await record_audit(
        db,
        action="NODE_HEALTH_CHECK",
        resource_type="node",
        resource_id=node.id,
        user_id=admin.id,
        result="success" if reachable else "failure",
    )
    await db.commit()

    return NodeHealthCheckResult(
        node_id=node.id, reachable=reachable, detail=detail, checked_at=utcnow()
    )
