"""Contracts for the photos a city or country shows: finding a cover, fetching an image, placing a city."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from sqlalchemy.ext.asyncio import AsyncSession

# Where the photo picker looks: the images of the city's Wikipedia article, or a Wikimedia Commons search.
CoverSource: TypeAlias = Literal["article", "commons"]


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


@dataclass(frozen=True)
class CoverCandidate:
    """One photo the picker offers: a Commons file, its 400 px thumbnail, its full size and the credit to show."""

    # "File:<name>": what `CoverPhotoProvider.from_file` takes.
    title: str
    thumb_url: str
    width: int
    height: int
    credit: str
    page_url: str


class CoverSourceUnavailableError(Exception):
    """Wikipedia or Commons could not be read for the picker."""


class CoverSourceBusyError(CoverSourceUnavailableError):
    """Wikimedia answered 429 (it limits quick successive calls): try again in a minute."""


class ImageFetcher(Protocol):
    async def fetch(self, url: str) -> FetchedImage | None:
        """The image at a public http(s) URL, or None when it can't be fetched or isn't an image (never raises)."""
        ...


class CoverPhotoProvider(Protocol):
    """Every call is logged in `integration.provider_calls` through the given session (when there is one)."""

    async def find(self, titles: list[str], session: AsyncSession | None = None) -> CoverPhoto | None:
        """The lead photo of the first article title that has one, or None (never raises)."""
        ...

    async def candidates(
        self, source: CoverSource, titles: list[str], query: str, session: AsyncSession | None = None,
    ) -> list[CoverCandidate]:
        """Photos to choose from: the first article title's images (`article`) or a Commons search for `query`
        (`commons`), JPEG/PNG/WebP at least 1200 px wide, no flags, maps or emblems. Raises
        CoverSourceUnavailableError (CoverSourceBusyError on a 429)."""
        ...

    async def from_file(self, file_title: str, session: AsyncSession | None = None) -> CoverPhoto | None:
        """A Commons file ("File:<name>") at 1600 px with its credit, or None (never raises)."""
        ...


class CityGeocoder(Protocol):
    async def geocode(
        self, city: str, country: str, country_code: str | None, session: AsyncSession | None = None,
    ) -> GeocodedCity | None:
        """Where a city is, preferring a match in the given country; None when unknown or unreachable (never raises).
        Logged in `integration.provider_calls` through the session, when there is one."""
        ...
