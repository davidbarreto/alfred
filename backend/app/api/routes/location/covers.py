from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status

from app.api.auth import require_auth
from app.dependencies import CoverServiceDep
from app.features.location.cities.schemas import CityRead
from app.features.location.countries.schemas import CountryRead
from app.features.location.covers import CoverNotFoundError
from app.shared.protocols.media import FetchedImage

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


@router.put("/cities/{city_id}/cover", response_model=CityRead)
async def set_city_cover(
    city_id: int, service: CoverServiceDep, file: UploadFile | None = File(None), url: str | None = Form(None),
) -> CityRead:
    """A multipart upload: either `file` (an image) or `url` (an image address, fetched once)."""
    city = await service.set_city_cover(city_id, data=await _upload(file), url=url)
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


@router.put("/countries/{country_id}/cover", response_model=CountryRead)
async def set_country_cover(
    country_id: int, service: CoverServiceDep, file: UploadFile | None = File(None), url: str | None = Form(None),
) -> CountryRead:
    country = await service.set_country_cover(country_id, data=await _upload(file), url=url)
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
