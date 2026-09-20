from pydantic import BaseModel, Field


class ExtensionInstall(BaseModel):
    name: str = Field(min_length=2, max_length=63)


class ExtensionResponse(BaseModel):
    name: str
    installed: bool
    version: str | None
