from pydantic import BaseModel, Field


class ProvisionDatabaseRequest(BaseModel):
    database_name: str = Field(min_length=3, max_length=63)
    role_name: str = Field(min_length=3, max_length=63)
    password: str = Field(min_length=8)


class ProvisionDatabaseResponse(BaseModel):
    status: str
    database_name: str


class CreateRoleRequest(BaseModel):
    role_name: str = Field(min_length=3, max_length=63)
    password: str = Field(min_length=8)
    scope: str = Field(pattern="^(app|readonly)$")


class RotateRoleRequest(BaseModel):
    password: str = Field(min_length=8)


class InstallExtensionRequest(BaseModel):
    name: str = Field(min_length=2, max_length=63)


class BackupRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=512)


class BackupResponse(BaseModel):
    status: str
    storage_key: str
    size_bytes: int


class RestoreRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=512)
    role_name: str = Field(min_length=3, max_length=63)
    password: str = Field(min_length=8)


class VerifyBackupRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=512)


class VerifyBackupResponse(BaseModel):
    verified: bool
    detail: str


class SetConnectionLimitRequest(BaseModel):
    limit: int = Field(ge=-1)


class QuiesceRequest(BaseModel):
    role_name: str = Field(min_length=3, max_length=63)
