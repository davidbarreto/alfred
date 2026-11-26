"""Where a city is, for its map marker, and which country it is in, for the country's ISO code.

Each lookup is logged in `integration.provider_calls` (operation `geocode_city`): the city asked for and the match's
coordinates and code."""
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.provider_calls.repository import create_sync_log
from app.shared.protocols.media import GeocodedCity

from .client import OpenMeteoClient

logger = logging.getLogger(__name__)


def pick(results: list[dict], country: str) -> dict | None:
    """The first result in the named country, else the first result."""
    key = country.strip().lower()
    for result in results:
        if (result.get("country") or "").strip().lower() == key:
            return result
    return results[0] if results else None


class OpenMeteoCityGeocoder:
    def __init__(self, client: OpenMeteoClient | None = None):
        self._client = client or OpenMeteoClient()

    async def geocode(
        self, city: str, country: str, country_code: str | None, session: AsyncSession | None = None,
    ) -> GeocodedCity | None:
        request = {"city": city, "country": country, "country_code": country_code}
        try:
            results = await self._client.search(city, country_code=country_code)
            if not results and country_code:
                results = await self._client.search(city)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("City geocoding failed: error=%s", exc)
            await _log(session, city, request, None, str(exc) or type(exc).__name__)
            return None
        geocoded = _geocoded(pick(results, country))
        response = {"results": len(results), "found": geocoded is not None}
        if geocoded is not None:
            response.update(latitude=geocoded.latitude, longitude=geocoded.longitude, country_code=geocoded.country_code)
        await _log(session, city, request, response, None)
        return geocoded


def _geocoded(found: dict | None) -> GeocodedCity | None:
    if found is None or found.get("latitude") is None or found.get("longitude") is None:
        return None
    code = (found.get("country_code") or "").upper() or None
    return GeocodedCity(latitude=float(found["latitude"]), longitude=float(found["longitude"]), country_code=code)


async def _log(session: AsyncSession | None, city: str, request: dict, response: dict | None, error: str | None) -> None:
    if session is None:
        return
    try:
        await create_sync_log(
            session, provider="open_meteo", operation="geocode_city", entity_type="city", provider_entity_id=city[:255],
            status="error" if error else "ok", request_payload=request, response_payload=response, error=error,
        )
    except Exception:
        logger.warning("Failed to write integration sync log", exc_info=True)
