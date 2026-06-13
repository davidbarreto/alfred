from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class MonitorBase(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    type: Literal["html_static", "html_javascript", "api"] = "html_static"
    url: str
    selector: str | None = None
    json_path: str | None = None
    target: str
    case_sensitive: bool = True
    timeout: int = Field(default=10, ge=1)
    page_size: int | None = Field(default=32, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    request_delay: int | None = Field(default=0, ge=0)
    wait_selector: str | None = None


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    type: Literal["html_static", "html_javascript", "api"] | None = None
    url: str | None = None
    selector: str | None = None
    json_path: str | None = None
    target: str | None = None
    case_sensitive: bool | None = None
    timeout: int | None = Field(default=None, ge=1)
    page_size: int | None = Field(default=None, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    request_delay: int | None = Field(default=None, ge=0)
    wait_selector: str | None = None


class MonitorRead(MonitorBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    monitor_id: int
    status: str
    result: str | None = None
    error: str | None = None
    config_snapshot: dict[str, Any]
    created_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    execution_id: int
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
