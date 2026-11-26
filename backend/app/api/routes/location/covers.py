from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import CoverServiceDep
from app.features.location.cities.schemas import CityRead
from app.features.location.countries.schemas import CountryRead
from app.features.location.cover_schemas import CoverCandidateRead
from app.features.location.covers import CoverNotFoundError
from app.shared.protocols.media import (
    CoverCandidate, CoverSource, CoverSourceBusyError, CoverSourceUnavailableError, FetchedImage,
)

# Invalid images or URLs (422) are mapped by main.py's location error handlers.
router = APIRouter(prefix="/location", tags=["location"], dependencies=[Depends(require_auth)])

_CITY_NOT_FOUND = "City not found"
_COUNTRY_NOT_FOUND = "Country not found"
# Covers change only when replaced, and the portal adds ?v=<updated_at> to their URL.
_CACHE = "private, max-age=86400"


def _image(image: FetchedImage | None, what: str) -> Response:
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} has no cover")
    return Response(content=image.data, media_type=image.content_type, headers={"Cache-Control": _CACHE})


async def _upload(file: UploadFile | None) -> bytes | None:
    return await file.read() if file is not None else None


async def _candidates(call) -> list[CoverCandidate] | None:
    """Wikimedia's 429 is a 503 the picker reads as "busy, try again in a minute"; anything else it can't read, 502."""
    try:
        return await call
    except CoverSourceBusyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except CoverSourceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


_Query = Annotated[str | None, Query(max_length=200, description="Commons search words (default: the name)")]


@router.post("/cities/{city_id}/cover/find", response_model=CityRead)
async def find_city_cover(city_id: int, service: CoverServiceDep) -> CityRead:
    """Use the lead photo of the city's Wikipedia article as its cover (replacing any)."""
    try:
        city = await service.find_city_cover(city_id)
    except CoverNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CITY_NOT_FOUND)
    return city


@router.get("/cities/{city_id}/cover/candidates", response_model=list[CoverCandidateRead])
async def city_cover_candidates(
    city_id: int, service: CoverServiceDep, source: CoverSource = "article", q: _Query = None,
) -> list[CoverCandidateRead]:
    """Photos to choose a cover from: the images of the city's Wikipedia article, or a Commons search."""
    found = await _candidates(service.city_cover_candidates(city_id, source, q))
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CITY_NOT_FOUND)
    return [CoverCandidateRead.model_validate(c) for c in found]


@router.put("/cities/{city_id}/cover", response_model=CityRead)
async def set_city_cover(
    city_id: int, service: CoverServiceDep, file: UploadFile | None = File(None), url: str | None = Form(None),
    commons_file: str | None = Form(None),
) -> CityRead:
    """A multipart upload: exactly one of `file` (an image), `url` (an image address, fetched once) or `commons_file`
    (a picker photo's "File:..." title, fetched at 1600 px with its credit)."""
    city = await service.set_city_cover(city_id, data=await _upload(file), url=url, commons_file=commons_file)
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CITY_NOT_FOUND)
    return city


@router.delete("/cities/{city_id}/cover", response_model=CityRead)
async def remove_city_cover(city_id: int, service: CoverServiceDep) -> CityRead:
    city = await service.remove_city_cover(city_id)
    if city is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_CITY_NOT_FOUND)
    return city


@router.get("/cities/{city_id}/cover", response_class=Response)
async def get_city_cover(city_id: int, service: CoverServiceDep) -> Response:
    return _image(await service.read_city_cover(city_id), "The city")


@router.get("/countries/{country_id}/cover/candidates", response_model=list[CoverCandidateRead])
async def country_cover_candidates(country_id: int, service: CoverServiceDep, q: _Query = None) -> list[CoverCandidateRead]:
    """A Commons search for the country's cover (its article's lead image is usually a flag)."""
    found = await _candidates(service.country_cover_candidates(country_id, q))
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_COUNTRY_NOT_FOUND)
    return [CoverCandidateRead.model_validate(c) for c in found]


@router.put("/countries/{country_id}/cover", response_model=CountryRead)
async def set_country_cover(
    country_id: int, service: CoverServiceDep, file: UploadFile | None = File(None), url: str | None = Form(None),
    commons_file: str | None = Form(None),
) -> CountryRead:
    """The same three kinds as a city's cover."""
    country = await service.set_country_cover(country_id, data=await _upload(file), url=url, commons_file=commons_file)
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_COUNTRY_NOT_FOUND)
    return country


@router.delete("/countries/{country_id}/cover", response_model=CountryRead)
async def remove_country_cover(country_id: int, service: CoverServiceDep) -> CountryRead:
    country = await service.remove_country_cover(country_id)
    if country is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_COUNTRY_NOT_FOUND)
    return country


@router.get("/countries/{country_id}/cover", response_class=Response)
async def get_country_cover(country_id: int, service: CoverServiceDep) -> Response:
    return _image(await service.read_country_cover(country_id), "The country")
