import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.tasks.schemas import TaskFilters
from app.features.organizer.tasks.service import TaskService

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


async def handle_assistant(
    command: str,
    arguments: dict[str, Any],
    task_service: TaskService,
    event_service: CalendarEventService,
) -> Any:
    logger.debug("handle_assistant: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "focus":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown assistant command: {command}")

    now = datetime.now(timezone.utc)
    today = now.date()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    all_tasks = await task_service.get_tasks(TaskFilters(status="ALL", limit=100))
    active = [t for t in all_tasks if t.status in ("TODO", "DOING")]

    def _sort_key(t: Any) -> tuple:
        overdue = 0 if (t.deadline and t.deadline.date() < today) else 1
        return (overdue, _PRIORITY_ORDER.get(t.priority, 99))

    active.sort(key=_sort_key)

    todays_events = await event_service.get_events(EventFilters(start_from=today_start, start_to=today_end, limit=10))

    logger.debug("handle_assistant focus: active_tasks=%d events_today=%d", len(active), len(todays_events))
    return {
        "tasks": [t.model_dump(mode='json') for t in active[:15]],
        "events_today": [e.model_dump(mode='json') for e in todays_events],
        "context": {
            "current_time": now.isoformat(),
            "task_count": len(active),
            "event_count": len(todays_events),
        },
    }
