import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.reminders.schemas import ReminderDigest
from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.organizer.calendar_events.notification_settings.service import (
    CalendarNotificationSettingsService,
)
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.shared.notification_offsets import parse_offset
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_LOOKAHEAD = timedelta(days=7)
_MATCH_WINDOW = timedelta(minutes=5)
# Long enough that the dedup marker survives until the next 5-min cron tick after
# it's written, short enough that the same event's NEXT offset tier can still fire
# once its own target time is reached.
_DEDUP_TTL = timedelta(hours=6)


class CalendarNotificationService:

    def __init__(self, session: AsyncSession, event_service: CalendarEventService) -> None:
        self._event_service = event_service
        self._settings = CalendarNotificationSettingsService(session)
        self._working_memory_repo = WorkingMemoryRepository(session)

    async def build_due_digest(self) -> ReminderDigest:
        now = local_now().replace(tzinfo=None)
        today = now.date()

        # A "0" (at-time) or small offset targets start_datetime <= now, so the
        # lower bound must reach slightly into the past -- not now itself -- or
        # an event that has just started is filtered out before it can match.
        events = await self._event_service.get_events(
            EventFilters(start_from=now - _MATCH_WINDOW, start_to=now + _LOOKAHEAD, limit=200)
        )

        lines: list[str] = []
        for event in events:
            profile = event.notification_profile or "normal"
            cascade = await self._settings.get_cascade(profile)
            for offset in cascade:
                if event.all_day and offset not in ("0",) and not offset.endswith(("d", "mo")):
                    continue
                target = event.start_datetime - parse_offset(offset)
                if not (target <= now < target + _MATCH_WINDOW):
                    continue
                dedup_key = f"calendar_notif:{event.id}:{profile}:{offset}:{event.start_datetime.isoformat()}"
                if await self._already_sent(dedup_key):
                    continue
                lines.append(_format_line(event, offset))
                await self._mark_sent(dedup_key)

        text = "\n".join(["📅 Event reminders", *lines]) if lines else ""
        return ReminderDigest(date=today, has_content=bool(lines), text=text)

    async def _already_sent(self, key: str) -> bool:
        existing = await self._working_memory_repo.list(
            WorkingMemoryFilters(key=key, expired="active", limit=1)
        )
        return bool(existing)

    async def _mark_sent(self, key: str) -> None:
        await self._working_memory_repo.upsert(
            WorkingMemoryCreate(key=key, value="sent", expires_at=datetime.now(timezone.utc) + _DEDUP_TTL)
        )


def _format_line(event, offset: str) -> str:
    when = "All day" if event.all_day else event.start_datetime.strftime("%a %H:%M")
    if offset == "0":
        return f"- Starting now: {event.title} ({when})"
    return f"- {event.title} in {_offset_label(offset)} ({when})"


def _offset_label(offset: str) -> str:
    unit_labels = {"mo": "month(s)", "d": "day(s)", "h": "hour(s)", "m": "minute(s)"}
    for suffix, label in unit_labels.items():
        if offset.endswith(suffix):
            amount = offset[: -len(suffix)]
            return f"{amount} {label}"
    return offset
