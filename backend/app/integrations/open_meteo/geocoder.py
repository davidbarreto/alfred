"""Where a city is, for its map marker, and which country it is in, for the country's ISO code."""
import logging

import httpx

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

    async def geocode(self, city: str, country: str, country_code: str | None) -> GeocodedCity | None:
        try:
            results = await self._client.search(city, country_code=country_code)
            if not results and country_code:
                results = await self._client.search(city)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("City geocoding failed: error=%s", exc)
            return None
        found = pick(results, country)
        if found is None or found.get("latitude") is None or found.get("longitude") is None:
            return None
        code = (found.get("country_code") or "").upper() or None
        return GeocodedCity(latitude=float(found["latitude"]), longitude=float(found["longitude"]), country_code=code)
