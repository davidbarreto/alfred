from __future__ import annotations

from datetime import date

import httpx

_BASE_URL = "https://api.frankfurter.dev/v1"


class FrankfurterClient:
    """Thin async wrapper around the Frankfurter REST API (ECB daily FX rates).

    Knows nothing about caching or business rules -- only HTTP and Frankfurter's
    wire format. A 404 response (no rate published for that date) is surfaced to
    the caller as an httpx.HTTPStatusError rather than swallowed here.
    """

    async def get_historical_rate(self, on_date: date, target_currency: str) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{_BASE_URL}/{on_date.isoformat()}",
                params={"from": "EUR", "to": target_currency},
            )
            response.raise_for_status()
            return response.json()
