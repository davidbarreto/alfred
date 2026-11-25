from app.shared.protocols.media import CoverPhoto, FetchedImage, GeocodedCity


class NullCoverPhotoProvider:
    """No-op CoverPhotoProvider: never finds a photo, without calling Wikipedia.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests): "Find photo" answers 404 and new cities get no cover.
    """

    async def find(self, titles: list[str]) -> CoverPhoto | None:
        return None


class NullImageFetcher:
    """No-op ImageFetcher: never fetches, so a pasted image URL is refused (422) in CI."""

    async def fetch(self, url: str) -> FetchedImage | None:
        return None


class NullCityGeocoder:
    """No-op CityGeocoder: new cities get no coordinates."""

    async def geocode(self, city: str, country: str, country_code: str | None) -> GeocodedCity | None:
        return None
