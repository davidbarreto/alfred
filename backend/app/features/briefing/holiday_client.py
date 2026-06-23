from __future__ import annotations

import logging
from datetime import date

import httpx

from app.features.briefing.schemas import HolidayItem

logger = logging.getLogger(__name__)

_BASE_URL = "https://date.nager.at/api/v3/PublicHolidays"
_COUNTRIES = ("PT", "BR")


class NagerDateHolidayClient:
    async def get_holidays(self, for_date: date) -> list[HolidayItem]:
        date_str = for_date.isoformat()
        results: list[HolidayItem] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for country in _COUNTRIES:
                try:
                    resp = await client.get(f"{_BASE_URL}/{for_date.year}/{country}")
                    resp.raise_for_status()
                    for entry in resp.json():
                        if entry.get("date") == date_str:
                            results.append(HolidayItem(
                                name=entry["name"],
                                local_name=entry["localName"],
                                country=country,
                            ))
                except Exception:
                    logger.warning("Failed to fetch holidays for %s", country, exc_info=True)

        return results
