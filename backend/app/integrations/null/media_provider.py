from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.protocols.media import CoverCandidate, CoverPhoto, CoverSource, FetchedImage, GeocodedCity


class NullCoverPhotoProvider:
    """No-op CoverPhotoProvider: never finds a photo, without calling Wikipedia.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests): "Find photo" answers 404, new cities get no cover, the
    picker offers nothing and a Commons file is refused (422).
    """

    async def find(self, titles: list[str], session: AsyncSession | None = None) -> CoverPhoto | None:
        return None

    async def candidates(
        self, source: CoverSource, titles: list[str], query: str, session: AsyncSession | None = None,
    ) -> list[CoverCandidate]:
        return []

    async def from_file(self, file_title: str, session: AsyncSession | None = None) -> CoverPhoto | None:
        return None


class NullImageFetcher:
    """No-op ImageFetcher: never fetches, so a pasted image URL is refused (422) in CI."""

    async def fetch(self, url: str) -> FetchedImage | None:
        return None


class NullCityGeocoder:
    """No-op CityGeocoder: new cities get no coordinates."""

    async def geocode(
        self, city: str, country: str, country_code: str | None, session: AsyncSession | None = None,
    ) -> GeocodedCity | None:
        return None
