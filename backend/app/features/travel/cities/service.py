import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityRead
from app.features.location.countries.repository import CountryRepository
from app.features.location.countries.schemas import CountryRead
from app.features.travel.cities.repository import TravelCityRepository
from app.features.travel.cities.schemas import CityDetail, CityPlace, CountryCity, CountryDetail, LocationTrip
from app.features.travel.default_tags import parse_default_tag_names
from app.features.travel.places.repository import TravelPlaceRepository
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.transaction_links.schemas import ChargePart, Cost, LinkedTransaction, LinkedTransactions, LocationCosts

logger = logging.getLogger(__name__)

_PLACES_SHOWN = 5


def _cost(row: tuple) -> Cost:
    total, count, unconverted = row
    return Cost(total_eur=total, transaction_count=count, unconverted_count=unconverted)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


async def is_home_city(settings: SettingService, city_id: int) -> bool:
    return (await settings.get_value("travel.home_city_id")) == str(city_id)


class TravelCityService:
    """Travel's read-only view of cities and countries: trips, places, grades and spend."""

    def __init__(self, session: AsyncSession):
        self._repo = TravelCityRepository(session)
        self._cities = CityRepository(session)
        self._countries = CountryRepository(session)
        self._place_repo = TravelPlaceRepository(session)
        self._cost_repo = TransactionLinkRepository(session)
        self._settings = SettingService(session)

    async def _city_grades(self, city_ids: list[int]) -> tuple[dict[int, list[int]], dict[int, float]]:
        """Each city's place ids and the mean grade of its graded places (cities with no graded place are absent)."""
        place_ids = await self._repo.get_place_ids_by_city(city_ids)
        grades = await self._place_repo.get_grades([p for ids in place_ids.values() for p in ids])
        means = {}
        for city_id, ids in place_ids.items():
            mean = _mean([grades[p][0] for p in ids if p in grades])
            if mean is not None:
                means[city_id] = mean
        return place_ids, means

    async def _charge_ids(self, place_ids: list[int], tag_groups: list[list[str]]) -> tuple[set[int], set[int]]:
        """Linked spend at the places, and charges carrying a group's tags that nothing else counts (any date)."""
        linked = await self._cost_repo.get_place_linked_ids(place_ids)
        tagged: set[int] = set()
        for names in tag_groups:
            tagged |= await self._cost_repo.get_unlinked_tagged_ids(names)
        return linked, tagged - linked

    async def _costs(self, place_ids: list[int], tag_groups: list[list[str]]) -> LocationCosts:
        linked, tagged = await self._charge_ids(place_ids, tag_groups)
        return LocationCosts(
            linked=_cost(await self._cost_repo.get_cost(linked)),
            tagged=_cost(await self._cost_repo.get_cost(tagged)),
            overall=_cost(await self._cost_repo.get_cost(linked | tagged)),
        )

    async def get_city_charges(self, city_id: int, part: ChargePart) -> LinkedTransactions | None:
        """The transactions behind a figure of the city's spend card."""
        city = await self._cities.get_city(city_id)
        if city is None:
            return None
        place_ids, _ = await self._city_grades([city_id])
        return await self._charges(place_ids[city_id], [parse_default_tag_names(city.default_tag_names)], part)

    async def get_country_charges(self, country_id: int, part: ChargePart) -> LinkedTransactions | None:
        country = await self._countries.get_country(country_id)
        if country is None:
            return None
        cities = await self._cities.get_country_cities(country_id)
        place_ids, _ = await self._city_grades([c.id for c in cities])
        tag_groups = [parse_default_tag_names(country.default_tag_names)] + [parse_default_tag_names(c.default_tag_names) for c in cities]
        return await self._charges([p for ids in place_ids.values() for p in ids], tag_groups, part)

    async def _charges(self, place_ids: list[int], tag_groups: list[list[str]], part: ChargePart) -> LinkedTransactions:
        linked, tagged = await self._charge_ids(place_ids, tag_groups)
        ids = {"linked": linked, "tagged": tagged, "overall": linked | tagged}[part]
        transactions = await self._cost_repo.get_transactions(ids)
        logger.debug("Location charges listed: part=%s count=%d", part, len(transactions))
        return LinkedTransactions(
            transactions=[LinkedTransaction.model_validate(t) for t in transactions],
            cost=_cost(await self._cost_repo.get_cost(ids)),
        )

    async def get_city_detail(self, city_id: int) -> CityDetail | None:
        city = await self._cities.get_city(city_id)
        if city is None:
            return None
        place_ids, means = await self._city_grades([city_id])
        ids = place_ids[city_id]
        grades = await self._place_repo.get_grades(ids)
        places = [
            CityPlace(id=p.id, name=p.name, kind=p.kind, grade=grades[p.id][0] if p.id in grades else None)
            for p in await self._repo.get_places(ids, _PLACES_SHOWN)
        ]
        trips = [LocationTrip.model_validate(t) for t in await self._repo.get_trips_of_cities([city_id])]
        return CityDetail(
            **CityRead.model_validate(city).model_dump(), grade=means.get(city_id),
            grade_count=len([p for p in ids if p in grades]), place_count=len(ids), places=places, trips=trips,
            home=await is_home_city(self._settings, city_id),
            costs=await self._costs(ids, [parse_default_tag_names(city.default_tag_names)]),
        )

    async def get_country_detail(self, country_id: int) -> CountryDetail | None:
        country = await self._countries.get_country(country_id)
        if country is None:
            return None
        cities = await self._cities.get_country_cities(country_id)
        place_ids, means = await self._city_grades([c.id for c in cities])
        trips = [LocationTrip.model_validate(t) for t in await self._repo.get_trips_of_cities([c.id for c in cities])]
        tag_groups = [parse_default_tag_names(country.default_tag_names)] + [parse_default_tag_names(c.default_tag_names) for c in cities]
        costs = await self._costs([p for ids in place_ids.values() for p in ids], tag_groups)
        return CountryDetail(
            **CountryRead.model_validate(country).model_dump(), costs=costs,
            grade=_mean(list(means.values())), grade_count=len(means),
            cities=[CountryCity(id=c.id, name=c.name, place_count=len(place_ids[c.id]), grade=means.get(c.id)) for c in cities],
            trips=trips,
        )
