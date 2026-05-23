from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class MonitorBase(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True
    type: Literal["html_static", "html_javascript", "api"] = "html_static"
    url: str
    selector: str | None = None  # For HTML monitoring
    json_path: str | None = None  # For API monitoring (e.g. "content", "data.items")
    target: str
    case_sensitive: bool = True
    timeout: int = Field(default=10, ge=1)
    # API-specific fields
    page_size: int | None = Field(default=32, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    request_delay: int | None = Field(default=0, ge=0)  # In milliseconds
    # JavaScript rendering fields
    wait_selector: str | None = None  # Selector to wait for before checking


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
    id: int

    class Config:
        orm_mode = True


class MonitorLogRead(BaseModel):
    id: int
    monitor_id: int
    created_at: datetime
    monitor_name: str | None = None
    monitor_description: str | None = None
    monitor_type: str
    url: str
    found: bool
    elements_checked: int
    error: str | None = None
    selector: str | None = None
    target: str | None = None
    case_sensitive: bool | None = None
    timeout: int | None = None
    page_size: int | None = None
    max_pages: int | None = None
    request_delay: int | None = None
    wait_selector: str | None = None
    json_path: str | None = None

    class Config:
        orm_mode = True
