import json
import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.contacts.notification_settings.schemas import (
    ContactBirthdayCascadeUpdate,
    ContactBirthdayCascadesRead,
)
from app.shared.notification_offsets import parse_offset

logger = logging.getLogger(__name__)

CASCADES_KEY = "organizer.contact_birthday_cascades"

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
        stored: dict[str, list[str]] = json.loads(raw) if raw is not None else {}
        relationships = {**DEFAULT_CASCADES, **stored}
        return ContactBirthdayCascadesRead(relationships=relationships)

    async def get_cascade(self, relationship: str | None) -> list[str]:
        settings = await self.get()
        return settings.relationships.get(relationship or "other", DEFAULT_CASCADES["other"])

    async def update_relationship(
        self, relationship: str, data: ContactBirthdayCascadeUpdate
    ) -> ContactBirthdayCascadesRead:
        for offset in data.offsets:
            try:
                parse_offset(offset)
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        current = await self.get()
        current.relationships[relationship] = data.offsets
        await self._settings.set_value(CASCADES_KEY, json.dumps(current.relationships))
        logger.info(
            "Birthday notification cascade updated: relationship=%s offsets=%s", relationship, data.offsets
        )
        return current
