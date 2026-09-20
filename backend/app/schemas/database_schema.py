from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool


class IndexInfo(BaseModel):
    name: str
    definition: str


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo]
    indexes: list[IndexInfo]
