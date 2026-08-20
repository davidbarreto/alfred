import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.reminders.schemas import ReminderDigest
from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.organizer.contacts.notification_settings.service import ContactBirthdaySettingsService
from app.features.organizer.contacts.repository import ContactRepository
from app.features.organizer.contacts.service import _next_birthday
from app.shared.notification_offsets import parse_offset
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

# Once-a-day dedup: birthdays have no time-of-day, so a marker just needs to
# outlive the rest of today, not survive until tomorrow's threshold check.
_DEDUP_TTL = timedelta(hours=20)


class ContactBirthdayNotificationService:

    def __init__(self, session: AsyncSession) -> None:
        # Reads synced contacts directly from the local table rather than going
        # through ContactService/live Google OAuth: birthday data is already
        # cached locally, so this check must not go silently empty just because
        # the Google Contacts token is missing or expired.
        self._contact_repo = ContactRepository(session)
        self._settings = ContactBirthdaySettingsService(session)
        self._working_memory_repo = WorkingMemoryRepository(session)

    async def build_due_digest(self) -> ReminderDigest:
        today = local_now().date()
        contacts = await self._contact_repo.get_all_with_birthday()

        lines: list[str] = []
        for contact in contacts:
            next_birthday = _next_birthday(contact.birthday, today)
            cascade = await self._settings.get_cascade(contact.relationship)
            for offset in cascade:
                threshold = next_birthday - parse_offset(offset)
                if threshold != today:
                    continue
                dedup_key = f"birthday_notif:{contact.id}:{offset}:{next_birthday.isoformat()}"
                if await self._already_sent(dedup_key):
                    continue
                lines.append(_format_line(contact.name, next_birthday, today))
                await self._mark_sent(dedup_key)

        text = "\n".join(["🎂 Birthday reminders", *lines]) if lines else ""
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


def _format_line(name: str, next_birthday, today) -> str:
    days_until = (next_birthday - today).days
    if days_until == 0:
        return f"- Today is {name}'s birthday!"
    return f"- {name}'s birthday in {days_until} day(s) ({next_birthday.strftime('%b %d')})"
