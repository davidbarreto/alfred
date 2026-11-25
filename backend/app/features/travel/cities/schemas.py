from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, computed_field

from app.features.location.cities.schemas import CityRead
from app.features.location.countries.schemas import CountryRead, CountryRef
from app.features.travel.transaction_links.schemas import LocationCosts
from app.shared.utils.links import photo_album_label, photos_search_url


class LocationTrip(BaseModel):
    """A trip that touches a city or country (a stay, a visit or a leg end there)."""

    id: int
    name: str
    start_date: date
    end_date: date
    photo_album_url: str | None = None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def photo_album_label(self) -> str | None:
        return photo_album_label(self.photo_album_url)


class CityPlace(BaseModel):
    id: int
    name: str
    kind: str
    grade: float | None = None


class CityDetail(CityRead):
    """Travel's view of a city: the base city plus its trips, places, grade and spend."""

    # It is the travel settings' home city.
    home: bool = False
    costs: LocationCosts = LocationCosts()
    # Derived, never stored: the mean of the grades of this city's graded places.
    grade: float | None = None
    grade_count: int = 0
    place_count: int = 0
    # The first five by name; the places page (`?city_id=`) lists them all.
    places: list[CityPlace] = []
    # Newest first.
    trips: list[LocationTrip] = []
    # Days of its trips so far (started trips, up to today) and the latest day something was done there.
    days: int = 0
    last_visit: date | None = None


class CountryCity(BaseModel):
    id: int
    name: str
    place_count: int = 0
    grade: float | None = None


class CountryDetail(CountryRead):
    """Travel's view of a country: the base country plus its cities' grades, trips and spend."""

    costs: LocationCosts = LocationCosts()
    # The mean of the grades of this country's graded cities.
    grade: float | None = None
    grade_count: int = 0
    cities: list[CountryCity] = []
    trips: list[LocationTrip] = []
    days: int = 0
    last_visit: date | None = None


TravelLocationSort = Literal["name", "trips", "days", "spend", "last_visit"]


class TravelLocationFilters:
    def __init__(
        self,
        q: Annotated[str | None, Query(description="Case-insensitive substring of the name")] = None,
        country_id: Annotated[int | None, Query(description="Cities only: those of this country")] = None,
        sort: Annotated[TravelLocationSort, Query()] = "name",
        desc: Annotated[bool, Query(description="Largest (or latest) first; name sorts A-Z unless set")] = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.q = q
        self.country_id = country_id
        self.sort = sort
        self.desc = desc
        self.limit = limit
        self.offset = offset


class TravelLocationRow(BaseModel):
    """One row of travel's city or country list: what was done there."""

    id: int
    name: str
    trips: int = 0
    # Days of its trips so far (started trips, up to today).
    days: int = 0
    spend_eur: Decimal = Decimal("0.00")
    last_visit: date | None = None

    @computed_field
    @property
    def photos_url(self) -> str:
        return photos_search_url(self.name)


class TravelCityRow(TravelLocationRow):
    country: CountryRef


class TravelCountryRow(TravelLocationRow):
    code: str | None = None
    # Its cities that have travel data.
    cities: int = 0
