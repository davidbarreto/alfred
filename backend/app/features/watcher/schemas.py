from datetime import datetime
from typing import Annotated, Any, Literal
from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field


class WatcherBase(BaseModel):
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


class WatcherCreate(WatcherBase):
    pass


class WatcherUpdate(BaseModel):
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


class WatcherRead(WatcherBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ExecutionFilters:
    def __init__(
        self,
        config_id: Annotated[int | None, Query()] = None,
        status: Annotated[str | None, Query()] = None,
        before_date: Annotated[datetime | None, Query()] = None,
        after_date: Annotated[datetime | None, Query()] = None,
        result: Annotated[str | None, Query()] = None,
        skip: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.config_id = config_id
        self.status = status
        self.before_date = before_date
        self.after_date = after_date
        self.result = result
        self.skip = skip
        self.limit = limit


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_id: int
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
    watcher_name: str | None = None
    target: str | None = None
    result: str | None = None


class AlertResolveRequest(BaseModel):
    alert_ids: list[int]


def build_alert_read(alert: Any) -> AlertRead:
    """Build an AlertRead enriched with denormalized fields from the linked execution."""
    execution = alert.execution
    snapshot = execution.config_snapshot if execution else {}
    return AlertRead(
        id=alert.id,
        execution_id=alert.execution_id,
        status=alert.status,
        created_at=alert.created_at,
        resolved_at=alert.resolved_at,
        watcher_name=snapshot.get("name") if execution else None,
        target=snapshot.get("target") if execution else None,
        result=execution.result if execution else None,
    )
