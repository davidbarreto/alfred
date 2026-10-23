from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CatchupKind = Literal["spread", "drop", "habits"]


class CatchupTask(BaseModel):
    id: int
    title: str
    priority: str
    urgency: str
    deadline: datetime | None = None
    days_overdue: int | None = None


class CatchupMove(BaseModel):
    task_id: int
    title: str
    priority: str
    old_deadline: datetime
    new_deadline: datetime


class CatchupSuggestion(BaseModel):
    kind: CatchupKind
    title: str
    detail: str
    # spread: the planned deadline moves; drop/habits: the tasks concerned
    moves: list[CatchupMove] = []
    tasks: list[CatchupTask] = []
    applicable: bool = True
    command: str | None = None


class CatchupRead(BaseModel):
    today_top: list[CatchupTask]
    suggestions: list[CatchupSuggestion]


class CatchupApply(BaseModel):
    kind: Literal["spread", "drop"]
    # drop only: a subset of the suggested tasks; omitted = every suggested task
    task_ids: list[int] | None = Field(default=None, min_length=1)


class CatchupApplyRead(BaseModel):
    kind: Literal["spread", "drop"]
    applied: int
    skipped: int
