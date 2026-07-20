from datetime import date, datetime
from typing import Annotated, Any, Literal, Optional, List
from pydantic import BaseModel, field_validator
from typing import Literal, TypeAlias
from fastapi import Query

TaskStatus: TypeAlias = Literal["TODO", "DOING", "DONE", "CANCELLED"]
TaskPriority: TypeAlias = Literal["LOW", "MEDIUM", "HIGH"]
TaskUrgency: TypeAlias = Literal["NORMAL", "URGENT"]

# Types for Filter
# "ACTIVE" excludes terminal states (DONE, CANCELLED) — used to hide finished tasks by default
TaskStatusFilter: TypeAlias = Literal["TODO", "DOING", "DONE", "CANCELLED", "ALL", "ACTIVE"]
TaskPriorityFilter: TypeAlias = Literal["LOW", "MEDIUM", "HIGH", "ALL"]
TaskUrgencyFilter: TypeAlias = Literal["NORMAL", "URGENT", "ALL"]

class TaskBase(BaseModel):
    title: str
    status: TaskStatus = "TODO"
    priority: TaskPriority = "LOW"
    urgency: TaskUrgency = "NORMAL"
    deadline: datetime | None = None
    tags: list[str] = []
    recurrence_rule: str | None = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    urgency: TaskUrgency | None = None
    deadline: datetime | None = None
    tags: list[str] | None = None
    recurrence_rule: str | None = None

class TaskRead(TaskBase):
    id: int
    created_at: datetime
    completed_at: datetime | None = None
    is_done_today: bool = False
    is_done_in_cycle: bool = False
    streak: int | None = None
    total_completions: int | None = None
    missed_count: int | None = None

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]

class TaskFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        status: Annotated[TaskStatusFilter, Query()] = "ALL",
        priority: Annotated[TaskPriorityFilter, Query()] = "ALL",
        urgency: Annotated[TaskUrgencyFilter, Query()] = "ALL",
        tags: Annotated[Optional[List[str]], Query()] = None,
        deadline_from: Annotated[Optional[datetime], Query()] = None,
        deadline_to: Annotated[Optional[datetime], Query()] = None,
        include_recurring: Annotated[bool, Query()] = False,
        due_today: Annotated[bool, Query()] = False,
    ) -> None:
        self.limit = limit
        self.status = status
        self.priority = priority
        self.urgency = urgency
        self.tags = tags
        self.deadline_from = deadline_from
        self.deadline_to = deadline_to
        self.include_recurring = include_recurring
        self.due_today = due_today

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TaskFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"TaskFilters(limit={self.limit}, status={self.status!r}, "
            f"priority={self.priority!r}, urgency={self.urgency!r}, "
            f"tags={self.tags!r}, deadline_from={self.deadline_from!r}, "
            f"deadline_to={self.deadline_to!r}, include_recurring={self.include_recurring!r}, "
            f"due_today={self.due_today!r})"
        )


class TaskCompletionRead(BaseModel):
    id: int
    task_id: int
    occurrence_date: date
    completed_at: datetime

    model_config = {"from_attributes": True}


class TaskSnoozeRead(BaseModel):
    id: int
    snoozed_until: datetime