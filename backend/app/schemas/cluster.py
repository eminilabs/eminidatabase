import datetime as dt
import uuid

from pydantic import BaseModel


class ClusterMemberResponse(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    role: str
    replication_lag_bytes: int | None
    promoted_at: dt.datetime | None

    model_config = {"from_attributes": True}


class ClusterResponse(BaseModel):
    id: uuid.UUID
    region_id: uuid.UUID
    topology: str
    shared: bool
    status: str
    members: list[ClusterMemberResponse]


class AddReplicaRequest(BaseModel):
    node_id: uuid.UUID


class FailoverResult(BaseModel):
    promoted_node_id: uuid.UUID
    databases_repointed: int
