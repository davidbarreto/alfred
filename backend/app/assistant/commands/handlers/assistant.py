import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.notes.schemas import NoteFilters
from app.features.organizer.notes.service import NoteService
from app.features.organizer.tasks.ranking import task_priority_sort_key
from app.features.organizer.tasks.schemas import TaskFilters
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_NOTES_CONTEXT_LIMIT = 15


async def handle_assistant(
    command: str,
    arguments: dict[str, Any],
    task_service: TaskService,
    event_service: CalendarEventService,
    note_service: NoteService,
) -> Any:
    logger.debug("handle_assistant: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "focus":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown assistant command: {command}")

    now = local_now().replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    all_tasks = await task_service.get_tasks(TaskFilters(status="ALL", limit=100))
    active = [t for t in all_tasks if t.status in ("TODO", "DOING")]
    active.sort(key=lambda t: task_priority_sort_key(t, now))

    todays_events = await event_service.get_events(EventFilters(start_from=today_start, start_to=today_end, limit=10))
    recent_notes = await note_service.get_notes(NoteFilters(limit=_NOTES_CONTEXT_LIMIT))

    logger.debug(
        "handle_assistant focus: active_tasks=%d events_today=%d notes=%d",
        len(active), len(todays_events), len(recent_notes),
    )
    return {
        "tasks": [t.model_dump(mode='json') for t in active[:15]],
        "events_today": [e.model_dump(mode='json') for e in todays_events],
        "notes": [n.model_dump(mode='json') for n in recent_notes],
        "context": {
            "current_time": now.isoformat(),
            "task_count": len(active),
            "event_count": len(todays_events),
        },
    }
