"""Cover photos of cities and countries: found on Wikipedia (cities only), uploaded, or fetched once from a pasted
image URL; stored under MEDIA_STORAGE_DIR (`covers/cities/<id>.<ext>`, `covers/countries/<id>.<ext>`), never hotlinked."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityRead
from app.features.location.cities.tables import City
from app.features.location.countries.repository import CountryRepository
from app.features.location.countries.schemas import CountryRead
from app.features.location.countries.tables import Country
from app.features.location.errors import LocationValidationError
from app.integrations.http.images import MAX_IMAGE_BYTES, sniff_image_type
from app.shared.protocols.audio import FileStorage
from app.shared.protocols.media import CoverPhoto, CoverPhotoProvider, FetchedImage, ImageFetcher

logger = logging.getLogger(__name__)

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


class CoverNotFoundError(Exception):
    """No photo could be found for the city (Wikipedia has none, or could not be reached)."""


def cover_titles(city: str, country: str) -> list[str]:
    """Wikipedia titles to try: "<City>, <Country>" first (homonyms such as Valencia), then the city alone."""
    return [f"{city}, {country}", city]


def _path(folder: str, owner_id: int, content_type: str) -> str:
    return f"covers/{folder}/{owner_id}.{_EXTENSIONS[content_type]}"


class CoverService:
    def __init__(self, session: AsyncSession, storage: FileStorage, photos: CoverPhotoProvider, images: ImageFetcher):
        self._cities = CityRepository(session)
        self._countries = CountryRepository(session)
        self._storage = storage
        self._photos = photos
        self._images = images

    # ---- cities -------------------------------------------------------------

    async def find_city_cover(self, city_id: int) -> CityRead | None:
        """Look the city up on Wikipedia and use its lead photo, replacing any cover. None when the city is unknown."""
        city = await self._cities.get_city(city_id)
        if city is None:
            return None
        photo = await self._photos.find(cover_titles(city.name, city.country.name))
        if photo is None:
            raise CoverNotFoundError(f"No photo found on Wikipedia for {city.name}")
        await self.apply_city_photo(city, photo)
        return CityRead.model_validate(city)

    async def apply_city_photo(self, city: City, photo: CoverPhoto) -> None:
        await self._store(self._cities, city, "cities", photo.image, photo.credit, photo.source_url)
        logger.info("City cover set: id=%d source=wikipedia", city.id)

    async def set_city_cover(self, city_id: int, data: bytes | None = None, url: str | None = None) -> CityRead | None:
        city = await self._cities.get_city(city_id)
        if city is None:
            return None
        await self._store(self._cities, city, "cities", await self._image(data, url), None, url)
        logger.info("City cover set: id=%d source=%s", city_id, "url" if url else "upload")
        return CityRead.model_validate(city)

    async def remove_city_cover(self, city_id: int) -> CityRead | None:
        city = await self._cities.get_city(city_id)
        if city is None:
            return None
        await self._clear(self._cities, city)
        logger.info("City cover removed: id=%d", city_id)
        return CityRead.model_validate(city)

    async def read_city_cover(self, city_id: int) -> FetchedImage | None:
        return await self._read(await self._cities.get_city(city_id))

    # ---- countries ----------------------------------------------------------

    async def set_country_cover(self, country_id: int, data: bytes | None = None, url: str | None = None) -> CountryRead | None:
        country = await self._countries.get_country(country_id)
        if country is None:
            return None
        await self._store(self._countries, country, "countries", await self._image(data, url), None, url)
        logger.info("Country cover set: id=%d source=%s", country_id, "url" if url else "upload")
        return CountryRead.model_validate(country)

    async def remove_country_cover(self, country_id: int) -> CountryRead | None:
        country = await self._countries.get_country(country_id)
        if country is None:
            return None
        await self._clear(self._countries, country)
        logger.info("Country cover removed: id=%d", country_id)
        return CountryRead.model_validate(country)

    async def read_country_cover(self, country_id: int) -> FetchedImage | None:
        return await self._read(await self._countries.get_country(country_id))

    # ---- shared -------------------------------------------------------------

    async def _image(self, data: bytes | None, url: str | None) -> FetchedImage:
        """The uploaded bytes or the image at the URL, checked to be a JPEG, PNG, WebP or GIF under the size cap."""
        if (data is None) == (url is None):
            raise LocationValidationError("Send exactly one of an image file or an image URL")
        if url is not None:
            image = await self._images.fetch(url.strip())
            if image is None:
                raise LocationValidationError("Could not fetch an image from that address")
            return image
        if len(data) > MAX_IMAGE_BYTES:
            raise LocationValidationError(f"The image is larger than {MAX_IMAGE_BYTES // 1_000_000} MB")
        content_type = sniff_image_type(data)
        if content_type is None:
            raise LocationValidationError("The file is not a JPEG, PNG, WebP or GIF image")
        return FetchedImage(data=data, content_type=content_type)

    async def _store(self, repo, owner: City | Country, folder: str, image: FetchedImage,
                     credit: str | None, source_url: str | None) -> None:
        path = _path(folder, owner.id, image.content_type)
        await self._storage.save(image.data, path)
        old = owner.cover_path
        await repo.update(owner, {"cover_path": path, "cover_credit": credit, "cover_source_url": source_url})
        if old and old != path:
            await self._storage.delete(old)

    async def _clear(self, repo, owner: City | Country) -> None:
        old = owner.cover_path
        await repo.update(owner, {"cover_path": None, "cover_credit": None, "cover_source_url": None})
        if old:
            await self._storage.delete(old)

    async def _read(self, owner: City | Country | None) -> FetchedImage | None:
        if owner is None or not owner.cover_path:
            return None
        data = await self._storage.read(owner.cover_path)
        content_type = sniff_image_type(data) if data else None
        return FetchedImage(data=data, content_type=content_type) if data and content_type else None


async def delete_cover_file(storage: FileStorage, path: str | None) -> None:
    """After a city or country is deleted, its cover file goes too."""
    if path:
        await storage.delete(path)

