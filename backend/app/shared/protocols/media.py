"""Contracts for the photos a city or country shows: finding a cover, fetching an image, placing a city."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FetchedImage:
    data: bytes
    # The type read from the bytes themselves (image/jpeg, image/png, image/webp, image/gif).
    content_type: str


@dataclass(frozen=True)
class CoverPhoto:
    image: FetchedImage
    # "Photo: <author>, <licence>, via Wikimedia Commons": what the licence asks to show next to the photo.
    credit: str
    source_url: str


@dataclass(frozen=True)
class GeocodedCity:
    latitude: float
    longitude: float
    # ISO 3166-1 alpha-2 of the country the match is in.
    country_code: str | None


class ImageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedImage | None:
        """The image at a public http(s) URL, or None when it can't be fetched or isn't an image (never raises)."""
        ...


class CoverPhotoProvider(Protocol):
    async def find(self, titles: list[str]) -> CoverPhoto | None:
        """The lead photo of the first article title that has one, or None (never raises)."""
        ...


class CityGeocoder(Protocol):
    async def geocode(self, city: str, country: str, country_code: str | None) -> GeocodedCity | None:
        """Where a city is, preferring a match in the given country; None when unknown or unreachable (never raises)."""
        ...
