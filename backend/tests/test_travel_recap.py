from datetime import date, datetime, time, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.features.travel.places.repository import PlaceRepository
from app.features.travel.places.schemas import PlaceFilters, PlaceRead
from app.features.travel.recap.builder import build_recap
from app.features.travel.recap.schemas import TripRecap
from app.features.travel.recap.service import TripRecapService
from app.features.travel.stays.schemas import StayRead
from app.features.travel.transaction_links.schemas import Cost, KindCost, TripCosts
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import TripDetail, TripFilters
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _place(name="Hotel Example", city="Lisbon", country="Portugal", kind="hotel"):
    return PlaceRead(
        id=3, kind=kind, name=name, city=city, country=country, maps_url=None, lat=None, lng=None, address=None, notes=None,
        created_at=NOW, updated_at=NOW,
    )


def _stay(id=7, grade=None, notes=None, place=None, check_in=datetime(2031, 12, 18, 14, tzinfo=timezone.utc)):
    place = place or _place()
    return StayRead(
        id=id, trip_id=1, place_id=place.id, place=place, check_in_at=check_in,
        check_out_at=check_in.replace(day=check_in.day + 2), timezone="UTC", booking_ref=None, booking_url=None,
        notes=notes, grade=grade, created_at=NOW, updated_at=NOW,
    )


def _visit(id=11, status="visited", grade=None, notes=None, name="Cafe Example", city="Porto", country="Portugal", day=date(2031, 12, 19)):
    return VisitRead(
        id=id, place_id=20 + id, place=VisitPlace(id=20 + id, kind="restaurant", name=name, city=city, country=country,
                                                 maps_url=None, lat=None, lng=None),
        trip_id=1, trip_name="Example trip", status=status, visit_date=day, visit_time=time(20, 0), notes=notes, grade=grade,
        created_at=NOW, updated_at=NOW,
    )


def _detail(visits=(), stays=(), legs=0):
    return TripDetail(
        id=1, name="Example trip", start_date=date(2031, 12, 17), end_date=date(2031, 12, 24), travelers=None, preferences=None,
        checklist_note_id=None, notes=None, default_tag_names=None, tags=[], created_at=NOW, updated_at=NOW,
        legs=[], stays=list(stays), timeline=[], warnings=[], visits=list(visits),
    )


COSTS = TripCosts(
    total=Cost(total_eur=Decimal("250.00"), transaction_count=3, unconverted_count=1),
    tagged=Cost(total_eur=Decimal("40.00"), transaction_count=2),
    overall=Cost(total_eur=Decimal("290.00"), transaction_count=5, unconverted_count=1),
    by_kind=[KindCost(kind="flight", total_eur=Decimal("120.00"), transaction_count=1)], legs=[], stays=[], visits=[],
)


class TestBuildRecap:
    def test_counts_days_and_visits_by_status(self):
        recap = build_recap(_detail(visits=[_visit(1), _visit(2), _visit(3, "missed"), _visit(4, "planned")], stays=[_stay()]), COSTS)
        assert (recap.days, recap.stay_count, recap.visits_visited, recap.visits_missed, recap.visits_planned) == (8, 1, 2, 1, 1)

    def test_spend_comes_from_the_costs(self):
        recap = build_recap(_detail(), COSTS)
        assert recap.spend.total_eur == Decimal("250.00") and recap.spend.unconverted_count == 1
        assert recap.spend_by_kind[0].kind == "flight"

    def test_tagged_charges_are_a_separate_part_with_the_overall_beside_it(self):
        recap = build_recap(_detail(), COSTS)
        assert recap.spend_tagged.total_eur == Decimal("40.00") and recap.spend_overall.total_eur == Decimal("290.00")

    def test_no_costs_means_zero_spend_not_missing(self):
        recap = build_recap(_detail(), None)
        assert recap.spend_tagged.total_eur == Decimal("0.00") and recap.spend_overall.transaction_count == 0
        assert recap.spend.total_eur == Decimal("0.00") and recap.spend.transaction_count == 0 and recap.spend_by_kind == []

    def test_cities_and_countries_come_from_stays_and_visited_visits_only(self):
        recap = build_recap(_detail(
            visits=[_visit(1, city="Porto"), _visit(2, status="missed", city="Faro", country="Spain")],
            stays=[_stay(place=_place(city="lisbon"))],
        ), None)
        assert recap.cities == ["lisbon", "Porto"] and recap.countries == ["Portugal"]

    def test_names_are_deduplicated_ignoring_case(self):
        recap = build_recap(_detail(stays=[_stay(1, place=_place(city="Lisbon")), _stay(2, place=_place(city="LISBON"))]), None)
        assert recap.cities == ["Lisbon"]

    def test_to_complete_lists_what_lacks_a_grade_or_notes(self):
        recap = build_recap(_detail(
            visits=[_visit(1, grade=4, notes="Nice"), _visit(2, grade=3), _visit(3, notes="Lovely"), _visit(4)],
            stays=[_stay(7, grade=5, notes="Quiet"), _stay(8, notes="x")],
        ), None)
        by_id = {(i.kind, i.id): i.missing for i in recap.to_complete}
        assert by_id == {("visit", 2): ["notes"], ("visit", 3): ["grade"], ("visit", 4): ["grade", "notes"], ("stay", 8): ["grade"]}

    def test_blank_notes_count_as_missing(self):
        recap = build_recap(_detail(visits=[_visit(1, grade=4, notes="   ")]), None)
        assert recap.to_complete[0].missing == ["notes"]

    def test_unvisited_visits_are_not_asked_for_a_grade(self):
        recap = build_recap(_detail(visits=[_visit(1, "planned"), _visit(2, "missed")]), None)
        assert recap.to_complete == []

    def test_to_complete_is_in_date_order_with_undated_last(self):
        recap = build_recap(_detail(visits=[_visit(1, day=None), _visit(2, day=date(2031, 12, 20)), _visit(3, day=date(2031, 12, 18))]), None)
        assert [i.id for i in recap.to_complete] == [3, 2, 1]

    def test_highlights_are_the_best_graded_first(self):
        recap = build_recap(_detail(
            visits=[_visit(1, grade=4, name="B Cafe"), _visit(2, grade=5, name="A Cafe"), _visit(3, grade=3, name="Meh")],
            stays=[_stay(7, grade=5, place=_place(name="Hotel Z"))],
        ), None)
        assert [(h.place_name, h.grade) for h in recap.highlights] == [("A Cafe", 5), ("Hotel Z", 5), ("B Cafe", 4)]


class TestRecapService:
    async def test_uses_every_visit_and_the_costs(self):
        svc = TripRecapService(AsyncMock())
        svc._trips, svc._links = AsyncMock(), AsyncMock()
        svc._trips.get_trip_detail.return_value = _detail(visits=[_visit(1)])
        svc._links.get_trip_costs.return_value = COSTS
        recap = await svc.get_recap(1)
        svc._trips.get_trip_detail.assert_awaited_once_with(1, include_all_visits=True)
        assert recap.visits_visited == 1 and recap.spend.transaction_count == 3

    async def test_unknown_trip(self):
        svc = TripRecapService(AsyncMock())
        svc._trips, svc._links = AsyncMock(), AsyncMock()
        svc._trips.get_trip_detail.return_value = None
        assert await svc.get_recap(9) is None


class TestRecapApi:
    @pytest.fixture
    def recap_service(self):
        import app.dependencies as deps
        from app.main import app

        service = AsyncMock()
        app.dependency_overrides[deps.get_trip_recap_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def test_recap(self, recap_service):
        client, service = recap_service
        service.get_recap.return_value = build_recap(_detail(visits=[_visit(1)]), COSTS)
        r = client.get("/travel/trips/1/recap", headers={"Authorization": "Bearer test-api-token"})
        body = r.json()
        assert r.status_code == 200 and body["spend"]["total_eur"] == "250.00" and body["to_complete"][0]["missing"] == ["grade", "notes"]

    def test_unknown_trip(self, recap_service):
        client, service = recap_service
        service.get_recap.return_value = None
        assert client.get("/travel/trips/1/recap", headers={"Authorization": "Bearer test-api-token"}).status_code == 404


class _Capture:
    def __init__(self):
        self.statement = None

    async def scalars(self, stmt):
        self.statement = stmt
        raise _Stop


class _Stop(Exception):
    pass


async def _sql(call) -> str:
    session = _Capture()
    try:
        await call(session)
    except _Stop:
        pass
    return str(session.statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestFilterSql:
    async def test_trip_city_and_country_look_at_stays_and_visits(self):
        sql = await _sql(lambda s: TripRepository(s).get_trips(TripFilters(status="all", city="Lisbon", country="Portugal"), date(2026, 6, 5)))
        assert "travel.stays" in sql and "travel.visits" in sql and "lower(travel.places.city) = 'lisbon'" in sql
        assert "lower(travel.places.country) = 'portugal'" in sql and " OR " in sql

    async def test_ungraded_places_are_those_without_any_grade(self):
        sql = await _sql(lambda s: PlaceRepository(s).get_places(PlaceFilters(ungraded=True)))
        assert "NOT IN" in sql and "UNION ALL" in sql

    def test_new_filter_defaults_are_plain_values(self):
        assert (TripFilters().city, TripFilters().country, PlaceFilters().ungraded) == (None, None, False)
