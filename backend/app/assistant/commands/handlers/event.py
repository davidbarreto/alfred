import logging
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_dt, parse_tags
from app.features.organizer.calendar_events.schemas import EventCreate, EventFilters, EventUpdate
from app.features.organizer.calendar_events.service import CalendarEventService
from app.shared.timezone import local_naive_now, local_timezone, local_timezone_name

logger = logging.getLogger(__name__)

_DEFAULT_LIST_DAYS = 14
_DATE_ONLY_LENGTH = 10


def _parse_local(value: Any, end_of_day: bool = False) -> datetime | None:
    """Parse an ISO value into naive local time; a date-only end value means the end of that day."""
    parsed = parse_dt(value)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(local_timezone()).replace(tzinfo=None)
    if end_of_day and isinstance(value, str) and len(value.strip()) == _DATE_ONLY_LENGTH:
        return datetime.combine(parsed.date(), time(23, 59, 59))
    return parsed


async def handle_event(command: str, arguments: dict[str, Any], service: CalendarEventService) -> Any:
    logger.debug("handle_event: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "add":
        # start_datetime: explicit -s/--start flag, or date extracted from title by NLP
        start_dt = parse_dt(arguments.get("start") or arguments.get("deadline"))
        if not start_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Event requires a start date. Use -s <date> or include a date in the title.",
            )
        end_dt = parse_dt(arguments.get("end")) or start_dt + timedelta(hours=1)
        payload = EventCreate(
            title=arguments.get("title", ""),
            start_datetime=start_dt,
            end_datetime=end_dt,
            description=arguments.get("additional_notes"),
            recurrence_rule=arguments.get("recurrence"),
            tags=parse_tags(arguments.get("tags")),
        )
        result = await service.create_event(payload)
        return result.model_dump(mode='json')

    if command == "list":
        date_range = arguments.get("date_range")
        start_arg, end_arg = arguments.get("start"), arguments.get("end")
        if isinstance(date_range, dict):
            start_arg = start_arg or date_range.get("start")
            end_arg = end_arg or date_range.get("end")
        start_from = _parse_local(start_arg) or local_naive_now()
        start_to = _parse_local(end_arg, end_of_day=True) or start_from + timedelta(days=_DEFAULT_LIST_DAYS)
        filters = EventFilters(
            limit=int(arguments.get("limit", 100)),
            start_from=start_from,
            start_to=start_to,
        )
        results = await service.get_events(filters)
        return {
            "timezone": local_timezone_name(),
            "events": [r.model_dump(mode="json", exclude={"timezone"}) for r in results],
        }

    if command == "update":
        event_id = int(arguments["id"])
        update_fields: dict[str, Any] = {}
        if "title" in arguments:
            update_fields["title"] = arguments["title"]
        if "start" in arguments:
            update_fields["start_datetime"] = parse_dt(arguments["start"])
        if "end" in arguments:
            update_fields["end_datetime"] = parse_dt(arguments["end"])
        if "additional_notes" in arguments:
            update_fields["description"] = arguments["additional_notes"]
        if "recurrence" in arguments:
            update_fields["recurrence_rule"] = arguments["recurrence"]
        if "tags" in arguments:
            update_fields["tags"] = parse_tags(arguments["tags"])
        result = await service.update_event(event_id, EventUpdate(**update_fields))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} not found")
        return result.model_dump(mode='json')

    if command == "delete":
        event_id = int(arguments["id"])
        await service.delete_event(event_id)
        return {"deleted": True, "id": event_id}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown event command: {command}")
