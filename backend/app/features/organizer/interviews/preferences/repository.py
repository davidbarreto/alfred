from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.preferences.schemas import InterviewPreferencesUpdate
from app.features.organizer.interviews.preferences.tables import InterviewPreferences


class InterviewPreferencesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preferences(self) -> InterviewPreferences:
        result = await self._session.execute(select(InterviewPreferences).order_by(InterviewPreferences.id).limit(1))
        preferences = result.scalars().first()
        if preferences is None:
            preferences = InterviewPreferences()
            self._session.add(preferences)
            await self._session.commit()
            await self._session.refresh(preferences)
        return preferences

    async def update_preferences(self, data: InterviewPreferencesUpdate) -> InterviewPreferences:
        preferences = await self.get_preferences()
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(preferences, field, value)
        await self._session.commit()
        await self._session.refresh(preferences)
        return preferences
