from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.preferences.repository import InterviewPreferencesRepository
from app.features.organizer.interviews.preferences.schemas import (
    InterviewPreferencesRead,
    InterviewPreferencesUpdate,
)

logger = logging.getLogger(__name__)


class InterviewPreferencesService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = InterviewPreferencesRepository(session)

    async def get_preferences(self) -> InterviewPreferencesRead:
        preferences = await self._repo.get_preferences()
        return InterviewPreferencesRead.model_validate(preferences)

    async def update_preferences(self, data: InterviewPreferencesUpdate) -> InterviewPreferencesRead:
        preferences = await self._repo.update_preferences(data)
        logger.info(
            "Interview preferences updated: fields=%s", list(data.model_dump(exclude_unset=True).keys())
        )
        return InterviewPreferencesRead.model_validate(preferences)
