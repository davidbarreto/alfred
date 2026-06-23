from __future__ import annotations

from datetime import date
from typing import Protocol

from app.features.briefing.schemas import HolidayItem


class HolidayProvider(Protocol):
    """Async interface for public holiday lookups.

    Swap the implementation (Nager.Date, static list, …) without
    touching the briefing service layer.
    """

    async def get_holidays(self, for_date: date) -> list[HolidayItem]: ...
