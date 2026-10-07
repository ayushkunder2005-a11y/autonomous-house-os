from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str
    timestamp: datetime


class Page(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int
