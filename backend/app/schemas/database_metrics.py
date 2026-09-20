from pydantic import BaseModel


class DatabaseMetricsResponse(BaseModel):
    size_bytes: int
    active_connections: int
    max_connections: int
