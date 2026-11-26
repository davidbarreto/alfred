from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, computed_field

from app.features.location.cities.schemas import CityRead, CityRef
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
    # Nights spent there so far (decision in docs/modules/travel.md) and the latest day something was done there.
    nights: int = 0
    last_visit: date | None = None
    # Stays at its places and legs that start or end there: the counts behind the stays and legs pages.
    stay_count: int = 0
    leg_count: int = 0


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
    nights: int = 0
    last_visit: date | None = None
    stay_count: int = 0


TravelLocationSort = Literal["name", "trips", "nights", "spend", "last_visit"]


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
    # Nights spent there so far: distinct local dates of its begun stays, up to today.
    nights: int = 0
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


class LocationPage:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.limit = limit
        self.offset = offset


class LocationStay(BaseModel):
    """A stay at one of a city's or country's places, for its stays page."""

    id: int
    trip_id: int | None
    trip_name: str | None = None
    place_id: int
    place_name: str
    place_kind: str
    city: CityRef
    check_in_local: datetime
    check_out_local: datetime
    nights: int


class LocationLeg(BaseModel):
    """A leg that starts or ends in a city, for its legs card and page."""

    id: int
    trip_id: int
    trip_name: str | None = None
    mode: str
    origin: str
    destination: str
    origin_city: CityRef | None = None
    destination_city: CityRef | None = None
    departs_local: datetime
    arrives_local: datetime
