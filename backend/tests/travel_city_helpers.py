"""Synthetic cities for travel tests: the same name always gets the same id, so id comparisons behave like the real data."""
from app.features.location.cities.schemas import CityRef
from app.features.location.countries.schemas import CountryRef

_CITY_IDS: dict[str, int] = {}
_COUNTRY_IDS: dict[str, int] = {}


def city_ref(name: str = "Lisbon", country: str = "Testland") -> CityRef:
    city_id = _CITY_IDS.setdefault(f"{name.lower()}|{country.lower()}", len(_CITY_IDS) + 1)
    country_id = _COUNTRY_IDS.setdefault(country.lower(), len(_COUNTRY_IDS) + 1)
    return CityRef(id=city_id, name=name, country=CountryRef(id=country_id, name=country, code=None))
