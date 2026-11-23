from __future__ import annotations

from datetime import date
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import HolidayItem


class HolidayProvider(Protocol):
    """Async interface for public holiday lookups.

    Swap the implementation (Nager.Date, static list, …) without
    touching the briefing service layer.
    """

    async def get_holidays(
        self, from_date: date, to_date: date, session: AsyncSession | None = None
    ) -> list[HolidayItem]: ...
