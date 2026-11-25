import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.calendar_events.schemas import NotificationProfile
from app.features.organizer.calendar_events.notification_settings.schemas import (
    CalendarNotificationCascadeUpdate,
    CalendarNotificationCascadesRead,
)

logger = logging.getLogger(__name__)

CASCADES_KEY = "organizer.calendar_notification_cascades"

DEFAULT_CASCADES: dict[str, list[str]] = {
    "cant_miss": ["7d", "3d", "1d", "4h", "1h", "30m", "10m", "5m", "0"],
    "important": ["1d", "4h", "1h", "15m", "0"],
    "normal": ["1h", "10m", "0"],
    "light": ["5m", "0"],
    "aware": ["3d", "1d"],
}


class CalendarNotificationSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> CalendarNotificationCascadesRead:
        raw = await self._settings.get_value(CASCADES_KEY)
        stored: dict[str, list[str]] = json.loads(raw) if raw else {}
        # A profile the app does not know (stored before the PUT checked it) is ignored, not served.
        profiles = {**DEFAULT_CASCADES, **{k: v for k, v in stored.items() if k in DEFAULT_CASCADES}}
        return CalendarNotificationCascadesRead(profiles=profiles)

    async def get_cascade(self, profile: str) -> list[str]:
        settings = await self.get()
        return settings.profiles.get(profile, DEFAULT_CASCADES["normal"])

    async def update_profile(
        self, profile: NotificationProfile, data: CalendarNotificationCascadeUpdate
    ) -> CalendarNotificationCascadesRead:
        current = await self.get()
        current.profiles[profile] = data.offsets
        await self._settings.set_value(CASCADES_KEY, json.dumps(current.profiles))
        logger.info("Calendar notification cascade updated: profile=%s offsets=%s", profile, data.offsets)
        return current
