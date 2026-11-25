import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.contacts.notification_settings.schemas import (
    DEFAULT_BIRTHDAY_DASHBOARD_DAYS,
    DEFAULT_BIRTHDAY_LOOKAHEAD_DAYS,
    BirthdayRelationship,
    ContactBirthdayCascadeUpdate,
    ContactBirthdayCascadesRead,
    ContactBirthdaySettingsUpdate,
)

logger = logging.getLogger(__name__)

CASCADES_KEY = "organizer.contact_birthday_cascades"
_LOOKAHEAD_DEFAULTS = {
    "birthday_lookahead_days": DEFAULT_BIRTHDAY_LOOKAHEAD_DAYS,
    "birthday_dashboard_days": DEFAULT_BIRTHDAY_DASHBOARD_DAYS,
}


def _key(field: str) -> str:
    return f"organizer.{field}"

DEFAULT_CASCADES: dict[str, list[str]] = {
    "family": ["1mo", "15d", "7d", "5d", "1d"],
    "relative": ["15d", "7d", "1d"],
    "friend": ["7d", "1d"],
    "other": ["3d"],
}


class ContactBirthdaySettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> ContactBirthdayCascadesRead:
        raw = await self._settings.get_value(CASCADES_KEY)
        stored: dict[str, list[str]] = json.loads(raw) if raw else {}
        # A relationship the app does not know (stored before the PUT checked it) is ignored, not served.
        relationships = {**DEFAULT_CASCADES, **{k: v for k, v in stored.items() if k in DEFAULT_CASCADES}}
        lookaheads = {}
        for field, default in _LOOKAHEAD_DEFAULTS.items():
            value = await self._settings.get_value(_key(field))
            lookaheads[field] = int(value) if value else default
        return ContactBirthdayCascadesRead(relationships=relationships, **lookaheads)

    async def update(self, data: ContactBirthdaySettingsUpdate) -> ContactBirthdayCascadesRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Birthday settings updated: fields=%s", list(changes))
        return await self.get()

    async def get_cascade(self, relationship: str | None) -> list[str]:
        settings = await self.get()
        return settings.relationships.get(relationship or "other", DEFAULT_CASCADES["other"])

    async def update_relationship(
        self, relationship: BirthdayRelationship, data: ContactBirthdayCascadeUpdate
    ) -> ContactBirthdayCascadesRead:
        current = await self.get()
        current.relationships[relationship] = data.offsets
        await self._settings.set_value(CASCADES_KEY, json.dumps(current.relationships))
        logger.info(
            "Birthday notification cascade updated: relationship=%s offsets=%s", relationship, data.offsets
        )
        return current
