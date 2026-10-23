"""Pure rules that turn the active task list into catchup suggestions."""
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.features.organizer.tasks.recurrence import is_pending_today

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_SPREAD_HORIZON_DAYS = 60
TOP_TASKS = 3


@dataclass
class PlannedMove:
    task: Any  # TaskRead
    new_deadline: datetime


def _rank(task: Any) -> tuple:
    return (
        _PRIORITY_ORDER.get(task.priority, len(_PRIORITY_ORDER)),
        0 if task.urgency == "URGENT" else 1,
        task.deadline or datetime.max,
    )


def days_overdue(task: Any, now: datetime) -> int | None:
    if task.deadline is None or task.deadline >= now:
        return None
    return (now - task.deadline).days


def top_tasks(tasks: list[Any], now: datetime, limit: int = TOP_TASKS) -> list[Any]:
    """What to do today: pending tasks that are overdue, due today or urgent."""
    end_of_today = datetime.combine(now.date(), datetime.max.time())
    candidates = [
        t for t in tasks
        if is_pending_today(t.recurrence_rule, t.is_done_in_cycle, now.date())
        and (t.urgency == "URGENT" or (t.deadline is not None and t.deadline <= end_of_today))
    ]
    return sorted(candidates, key=_rank)[:limit]


def stale_tasks(tasks: list[Any], now: datetime, now_aware: datetime, stale_days: int) -> list[Any]:
    """Non-HIGH one-off tasks that have been overdue (or, undated, urgent) for a long time."""
    threshold = timedelta(days=stale_days)
    stale = []
    for t in tasks:
        if t.recurrence_rule is not None or t.priority == "HIGH":
            continue
        if t.deadline is not None:
            if now - t.deadline >= threshold:
                stale.append(t)
        elif t.urgency == "URGENT" and now_aware - t.created_at >= threshold:
            stale.append(t)
    return sorted(stale, key=lambda t: (t.deadline or datetime.max, t.created_at))


def missed_habits(tasks: list[Any], threshold: int) -> list[Any]:
    habits = [t for t in tasks if t.recurrence_rule is not None and (t.missed_count or 0) >= threshold]
    return sorted(habits, key=lambda t: -(t.missed_count or 0))


def plan_spread(
    tasks: list[Any], now: datetime, per_day: int, exclude_ids: set[int]
) -> list[PlannedMove]:
    """Re-date overdue one-off tasks so that no day gets more than `per_day` due tasks.

    Starts tomorrow, keeps each task's time of day, and counts tasks already due on a day
    toward its capacity. Most important (HIGH, then oldest deadline) goes first.
    """
    overdue = sorted(
        (
            t for t in tasks
            if t.recurrence_rule is None and t.deadline is not None and t.deadline < now and t.id not in exclude_ids
        ),
        key=lambda t: (_PRIORITY_ORDER.get(t.priority, len(_PRIORITY_ORDER)), t.deadline),
    )
    tomorrow = now.date() + timedelta(days=1)
    load: Counter[date] = Counter(
        t.deadline.date() for t in tasks
        if t.recurrence_rule is None and t.deadline is not None and t.deadline.date() >= tomorrow
    )

    moves: list[PlannedMove] = []
    day = tomorrow
    last_day = tomorrow + timedelta(days=_SPREAD_HORIZON_DAYS)
    for task in overdue:
        while load[day] >= per_day and day <= last_day:
            day += timedelta(days=1)
        if day > last_day:
            break
        moves.append(PlannedMove(task=task, new_deadline=datetime.combine(day, task.deadline.time())))
        load[day] += 1
    return moves
