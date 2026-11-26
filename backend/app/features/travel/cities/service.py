import logging
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.repository import CityRepository
from app.features.location.countries.repository import CountryRepository
from app.features.location.places.repository import PlaceRepository
from app.features.travel.cities.repository import TravelCityRepository
from app.features.location.cities.schemas import CityFilters, CityRef
from app.features.travel.cities.schemas import (
    CityDetail,
    CityPlace,
    CountryCity,
    CountryDetail,
    LocationLeg,
    LocationPage,
    LocationStay,
    LocationTrip,
    TravelCityRow,
    TravelCountryRow,
    TravelLocationFilters,
    TravelLocationRow,
)
from app.features.travel.constants import CITY_STATUS_GROUPS, CITY_STATUSES, CityStatus
from app.features.travel.trips.tables import Trip
from app.features.travel.zones import to_local
from app.shared.utils.timezone import local_today
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


def stay_nights(check_in_at: datetime, check_out_at: datetime, zone: str, today: date) -> set[date]:
    """The local dates a stay has covered so far: from its check-in date up to, not including, its check-out date,
    none after today (a stay that has not begun has none)."""
    start = to_local(check_in_at, zone).date()
    end = min(to_local(check_out_at, zone).date(), today + timedelta(days=1))
    return {start + timedelta(days=i) for i in range((end - start).days)}


def nights_by_city(spans: list[tuple[int, datetime, datetime, str]], today: date) -> dict[int, set[date]]:
    """City id -> the distinct dates of its stays so far (overlapping stays count once)."""
    found: dict[int, set[date]] = {}
    for city_id, check_in_at, check_out_at, zone in spans:
        found.setdefault(city_id, set()).update(stay_nights(check_in_at, check_out_at, zone, today))
    return found


def _union(nights: dict[int, set[date]], city_ids: list[int]) -> int:
    return len(set().union(*(nights.get(i, set()) for i in city_ids)))


def last_visit(trips: list, local: date | None, today: date) -> date | None:
    """The later of the last started trip's start and the last local visit or stay."""
    days = [t.start_date for t in trips if t.start_date <= today] + ([local] if local else [])
    return max(days) if days else None


def city_status(city_id: int, home_id: int | None, visited: set[int], planned: set[int], legs: set[int]) -> CityStatus:
    """The city's one travel status, best first: home, visited, planned, passed (only a leg end), none (only links)."""
    if city_id == home_id:
        return "home"
    for status, ids in (("visited", visited), ("planned", planned), ("passed", legs)):
        if city_id in ids:
            return status
    return "none"


def best_status(statuses: list[CityStatus]) -> CityStatus:
    """A country's status: its best city's."""
    return min(statuses, key=CITY_STATUSES.index, default="none")


def sort_rows(rows: list[TravelLocationRow], filters: TravelLocationFilters) -> list[TravelLocationRow]:
    """Sorted by the chosen column (rows with no last visit go last), then by name; then paginated."""
    if filters.q and filters.q.strip():
        key = filters.q.strip().lower()
        rows = [r for r in rows if key in r.name.lower()]
    if filters.status != "all":
        rows = [r for r in rows if r.status in CITY_STATUS_GROUPS[filters.status]]
    rows = sorted(rows, key=lambda r: r.name.lower())
    if filters.sort == "last_visit":
        dated = sorted((r for r in rows if r.last_visit), key=lambda r: r.last_visit, reverse=filters.desc)
        rows = dated + [r for r in rows if not r.last_visit]
    elif filters.sort != "name":
        rows = sorted(rows, key=lambda r: getattr(r, "spend_eur" if filters.sort == "spend" else filters.sort), reverse=filters.desc)
    elif filters.desc:
        rows.reverse()
    return rows[filters.offset:filters.offset + filters.limit]


async def is_home_city(places: PlaceRepository, city_id: int) -> bool:
    """The home city is the Home place's city."""
    home = await places.get_home()
    return home is not None and home.city_id == city_id


class TravelCityService:
    """Travel's read-only view of cities and countries: trips, places, grades and spend."""

    def __init__(self, session: AsyncSession):
        self._repo = TravelCityRepository(session)
        self._cities = CityRepository(session)
        self._countries = CountryRepository(session)
        self._place_repo = TravelPlaceRepository(session)
        self._cost_repo = TransactionLinkRepository(session)
        self._places = PlaceRepository(session)

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
        trip_rows = await self._repo.get_trips_of_cities([city_id])
        today = local_today()
        local = (await self._repo.get_last_local_visits([city_id], today)).get(city_id)
        nights = nights_by_city(await self._repo.get_stay_spans([city_id]), today)
        return CityDetail.model_validate(city).model_copy(update=dict(
            grade=means.get(city_id), grade_count=len([p for p in ids if p in grades]), place_count=len(ids),
            places=places, trips=[LocationTrip.model_validate(t) for t in trip_rows],
            nights=_union(nights, [city_id]), last_visit=last_visit(trip_rows, local, today),
            stay_count=await self._repo.count_stays([city_id]), leg_count=await self._repo.count_leg_ends(city_id),
            home=await is_home_city(self._places, city_id),
            costs=await self._costs(ids, [parse_default_tag_names(city.default_tag_names)]),
        ))

    async def get_country_detail(self, country_id: int) -> CountryDetail | None:
        country = await self._countries.get_country(country_id)
        if country is None:
            return None
        cities = await self._cities.get_country_cities(country_id)
        place_ids, means = await self._city_grades([c.id for c in cities])
        trip_rows = await self._repo.get_trips_of_cities([c.id for c in cities])
        today = local_today()
        locals_ = (await self._repo.get_last_local_visits([c.id for c in cities], today)).values()
        nights = nights_by_city(await self._repo.get_stay_spans([c.id for c in cities]), today)
        trips = [LocationTrip.model_validate(t) for t in trip_rows]
        tag_groups = [parse_default_tag_names(country.default_tag_names)] + [parse_default_tag_names(c.default_tag_names) for c in cities]
        costs = await self._costs([p for ids in place_ids.values() for p in ids], tag_groups)
        return CountryDetail.model_validate(country).model_copy(update=dict(
            costs=costs, grade=_mean(list(means.values())), grade_count=len(means),
            cities=[CountryCity(id=c.id, name=c.name, place_count=len(place_ids[c.id]), grade=means.get(c.id)) for c in cities],
            trips=trips, nights=_union(nights, [c.id for c in cities]), stay_count=await self._repo.count_stays([c.id for c in cities]),
            last_visit=last_visit(trip_rows, max(locals_, default=None), today),
        ))

    # ---- the travel lists ---------------------------------------------------

    async def _trips_by_city(self, city_ids: list[int]) -> dict[int, list[Trip]]:
        pairs = await self._repo.get_trip_city_pairs(city_ids)
        trips = {t.id: t for t in await self._repo.get_trips({trip_id for trip_id, _ in pairs})}
        found: dict[int, list[Trip]] = {i: [] for i in city_ids}
        for trip_id, city_id in pairs:
            found[city_id].append(trips[trip_id])
        return found

    async def _statuses(self) -> tuple[set[int], dict[int, CityStatus]]:
        """The ids of the cities with travel data plus the home city, and each one's status."""
        home = await self._places.get_home()
        home_id = home.city_id if home else None
        ids = await self._repo.get_travel_city_ids() | ({home_id} if home_id else set())
        visited, planned, legs = await self._repo.get_status_city_ids()
        return ids, {i: city_status(i, home_id, visited, planned, legs) for i in ids}

    async def list_cities(self, filters: TravelLocationFilters) -> list[TravelCityRow]:
        """The home city and cities with travel data (a stay, a visit, a leg end or a link): status, trips, nights, spend."""
        ids, statuses = await self._statuses()
        cities = [c for c in await self._cities.get_cities(CityFilters(country_id=filters.country_id)) if c.id in ids]
        city_ids = [c.id for c in cities]
        today = local_today()
        trips, locals_ = await self._trips_by_city(city_ids), await self._repo.get_last_local_visits(city_ids, today)
        nights = nights_by_city(await self._repo.get_stay_spans(city_ids), today)
        place_ids = await self._repo.get_place_ids_by_city(city_ids)
        rows = []
        for city in cities:
            costs = await self._costs(place_ids[city.id], [parse_default_tag_names(city.default_tag_names)])
            rows.append(TravelCityRow(
                id=city.id, name=city.name, country=city.country, status=statuses[city.id], trips=len(trips[city.id]),
                nights=_union(nights, [city.id]), spend_eur=costs.overall.total_eur,
                last_visit=last_visit(trips[city.id], locals_.get(city.id), today),
            ))
        logger.debug("Travel cities listed: count=%d", len(rows))
        return sort_rows(rows, filters)

    async def list_countries(self, filters: TravelLocationFilters) -> list[TravelCountryRow]:
        """Countries with travel data (one of their cities has some or is the home city, or a link of their own)."""
        city_ids, statuses = await self._statuses()
        all_cities = await self._cities.get_cities(CityFilters())
        travel_cities = [c for c in all_cities if c.id in city_ids]
        country_ids = {c.country_id for c in travel_cities} | await self._repo.get_link_country_ids()
        countries = [c for c in await self._countries.get_countries() if c.id in country_ids]
        today = local_today()
        ids = [c.id for c in travel_cities]
        trips, locals_ = await self._trips_by_city(ids), await self._repo.get_last_local_visits(ids, today)
        nights = nights_by_city(await self._repo.get_stay_spans(ids), today)
        place_ids = await self._repo.get_place_ids_by_city([c.id for c in all_cities])
        rows = []
        for country in countries:
            cities = [c for c in all_cities if c.country_id == country.id]
            country_trips = list({t.id: t for c in cities for t in trips.get(c.id, [])}.values())
            tag_groups = [parse_default_tag_names(country.default_tag_names)] + [parse_default_tag_names(c.default_tag_names) for c in cities]
            costs = await self._costs([p for c in cities for p in place_ids[c.id]], tag_groups)
            local = max((locals_[c.id] for c in cities if c.id in locals_), default=None)
            rows.append(TravelCountryRow(
                id=country.id, name=country.name, code=country.code, cities=len([c for c in cities if c.id in city_ids]),
                status=best_status([statuses[c.id] for c in cities if c.id in statuses]),
                trips=len(country_trips), nights=_union(nights, [c.id for c in cities]), spend_eur=costs.overall.total_eur,
                last_visit=last_visit(country_trips, local, today),
            ))
        logger.debug("Travel countries listed: count=%d", len(rows))
        return sort_rows(rows, filters)

    # ---- stays and legs pages -------------------------------------------------

    async def list_city_stays(self, city_id: int, page: LocationPage) -> list[LocationStay] | None:
        if await self._cities.get_city(city_id) is None:
            return None
        return await self._stays([city_id], page)

    async def list_country_stays(self, country_id: int, page: LocationPage) -> list[LocationStay] | None:
        if await self._countries.get_country(country_id) is None:
            return None
        return await self._stays([c.id for c in await self._cities.get_country_cities(country_id)], page)

    async def _stays(self, city_ids: list[int], page: LocationPage) -> list[LocationStay]:
        stays = await self._repo.get_stays(city_ids, page.limit, page.offset)
        names = await self._repo.get_trip_names({s.trip_id for s in stays if s.trip_id is not None})
        rows = []
        for stay in stays:
            check_in, check_out = to_local(stay.check_in_at, stay.timezone), to_local(stay.check_out_at, stay.timezone)
            rows.append(LocationStay(
                id=stay.id, trip_id=stay.trip_id, trip_name=names.get(stay.trip_id), place_id=stay.place_id,
                place_name=stay.place.name, place_kind=stay.place.kind, city=CityRef.model_validate(stay.place.city),
                check_in_local=check_in, check_out_local=check_out, nights=max((check_out.date() - check_in.date()).days, 0),
            ))
        logger.debug("Location stays listed: count=%d", len(rows))
        return rows

    async def list_city_legs(self, city_id: int, page: LocationPage) -> list[LocationLeg] | None:
        """Legs that start or end in the city, newest first."""
        if await self._cities.get_city(city_id) is None:
            return None
        legs = await self._repo.get_legs(city_id, page.limit, page.offset)
        names = await self._repo.get_trip_names({leg.trip_id for leg in legs})
        logger.debug("City legs listed: city_id=%d count=%d", city_id, len(legs))
        return [
            LocationLeg(
                id=leg.id, trip_id=leg.trip_id, trip_name=names.get(leg.trip_id), mode=leg.mode, origin=leg.origin,
                destination=leg.destination,
                origin_city=CityRef.model_validate(leg.origin_city) if leg.origin_city else None,
                destination_city=CityRef.model_validate(leg.destination_city) if leg.destination_city else None,
                departs_local=to_local(leg.departs_at, leg.departs_tz), arrives_local=to_local(leg.arrives_at, leg.arrives_tz),
            )
            for leg in legs
        ]
