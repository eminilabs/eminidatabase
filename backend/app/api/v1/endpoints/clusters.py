from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_platform_admin
from app.db.session import get_db
from app.models.cluster import Cluster
from app.models.cluster_member import ClusterMember
from app.models.node import Node
from app.models.user import User
from app.schemas.cluster import (
    AddReplicaRequest,
    ClusterMemberResponse,
    ClusterResponse,
    FailoverResult,
)
from app.services.agent_client import AgentUnreachableError
from app.services.ha_orchestrator import NoHealthyReplicaError, add_replica, execute_failover

router = APIRouter(prefix="/clusters", tags=["clusters"])


async def _to_response(db: AsyncSession, cluster: Cluster) -> ClusterResponse:
    members = (
        (await db.execute(select(ClusterMember).where(ClusterMember.cluster_id == cluster.id)))
        .scalars()
        .all()
    )
    return ClusterResponse(
        id=cluster.id,
        region_id=cluster.region_id,
        topology=cluster.topology.value,
        shared=cluster.shared,
        status=cluster.status.value,
        members=[ClusterMemberResponse.model_validate(m) for m in members],
    )


@router.get("/{cluster_id}", response_model=ClusterResponse)
async def get_cluster(
    cluster_id: uuid.UUID,
    _: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ClusterResponse:
    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    return await _to_response(db, cluster)


@router.post(
    "/{cluster_id}/replicas",
    response_model=ClusterMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def attach_replica(
    cluster_id: uuid.UUID,
    payload: AddReplicaRequest,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> ClusterMember:
    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    node = await db.get(Node, payload.node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")

    try:
        member = await add_replica(db, cluster, node)
    except AgentUnreachableError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach node: {exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(member)
    return member


@router.post("/{cluster_id}/failover", response_model=FailoverResult)
async def trigger_failover(
    cluster_id: uuid.UUID,
    admin: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> FailoverResult:
    """Manual trigger — cf. Phase 6 exit criterion ('test de panne simulée'). The
    automatic path (scheduler detecting a dead primary) calls the same
    app.services.ha_orchestrator.execute_failover underneath."""
    cluster = await db.get(Cluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")

    try:
        result = await execute_failover(db, cluster_id, automatic=False)
    except NoHealthyReplicaError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.commit()
    return FailoverResult(
        promoted_node_id=uuid.UUID(result["promoted_node_id"]),
        databases_repointed=result["databases_repointed"],
    )
