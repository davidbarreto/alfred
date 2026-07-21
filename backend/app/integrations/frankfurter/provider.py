from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log

from .client import FrankfurterClient

logger = logging.getLogger(__name__)

# The euro was introduced on 1999-01-04; Frankfurter has no rates before that date.
_EURO_EPOCH = date(1999, 1, 4)

# ECB doesn't publish a rate for weekends/holidays, and today's rate isn't published
# until the ECB's ~16:00 CET reference-rate release. Frankfurter 404s for those dates
# instead of falling back on its own, so step back a few business days ourselves.
_MAX_LOOKBACK_DAYS = 7


class FrankfurterProvider:
    def __init__(self, client: FrankfurterClient) -> None:
        self._client = client

    async def get_rate(
        self,
        currency: str,
        on_date: date,
        session: AsyncSession | None = None,
    ) -> Decimal | None:
        if on_date < _EURO_EPOCH:
            logger.warning("Frankfurter rate skipped: date=%s before euro introduction", on_date)
            return None

        probe = on_date
        error: str | None = None
        response_payload: dict | None = None
        rate: Decimal | None = None

        for _ in range(_MAX_LOOKBACK_DAYS + 1):
            try:
                response_payload = await self._client.get_historical_rate(probe, currency)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    probe -= timedelta(days=1)
                    continue
                error = str(exc)
                break
            except httpx.HTTPError as exc:
                error = str(exc)
                break

            value = response_payload.get("rates", {}).get(currency)
            if value is None:
                error = f"No rate for currency={currency!r} in response"
            else:
                rate = Decimal(str(value))
            break
        else:
            error = f"No rate published within {_MAX_LOOKBACK_DAYS} days of {on_date.isoformat()}"

        await self._write_log(session, currency, on_date, response_payload, error)
        return rate

    async def _write_log(
        self,
        session: AsyncSession | None,
        currency: str,
        on_date: date,
        response_payload: dict | None,
        error: str | None,
    ) -> None:
        if session is None:
            return
        try:
            await create_sync_log(
                session,
                provider="frankfurter",
                operation="get_rate",
                entity_type="exchange_rate",
                provider_entity_id=f"{currency}:{on_date.isoformat()}",
                status="error" if error else "ok",
                request_payload={"date": on_date.isoformat(), "currency": currency},
                response_payload=response_payload,
                error=error,
            )
        except Exception:
            logger.warning("Failed to write integration sync log", exc_info=True)
