from datetime import date

from pydantic import BaseModel

from app.features.location.cities.schemas import CityRead
from app.features.location.countries.schemas import CountryRead
from app.features.travel.transaction_links.schemas import LocationCosts


class LocationTrip(BaseModel):
    """A trip that touches a city or country (a stay, a visit or a leg end there)."""

    id: int
    name: str
    start_date: date
    end_date: date

    model_config = {"from_attributes": True}


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
