from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.detail import PlaceDetail
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.places.service import PlaceInUseError
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.schemas import TravelTagRead, TravelTagUsage
from app.features.travel.tags.service import TravelTagNameTakenError
from app.features.travel.trips.schemas import TripDetail, TripRead
from app.features.travel.visits.schemas import VisitPlace, VisitRead

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _trip(id=1) -> TripRead:
    return TripRead(
        id=id, name="Example trip", start_date=date(2026, 12, 17), end_date=date(2026, 12, 24), travelers=None,
        preferences=None, checklist_note_id=None, notes=None, default_tag_names=None, tags=["Family"],
        created_at=NOW, updated_at=NOW,
    )


def _leg(id=1) -> LegRead:
    return LegRead(
        id=id, trip_id=1, mode="flight", origin="A", destination="B", origin_code=None, destination_code=None,
        departs_at=datetime(2026, 12, 17, 6, tzinfo=timezone.utc), arrives_at=datetime(2026, 12, 17, 9, tzinfo=timezone.utc),
        departs_tz="UTC", arrives_tz="Europe/Stockholm", carrier="XX", number="12", booking_ref=None, booking_url=None,
        seat=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _place(id=3) -> PlaceRead:
    return PlaceRead(
        id=id, kind="hotel", name="Hotel Example", city="Lisbon", country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _stay(id=7) -> StayRead:
    return StayRead(
        id=id, trip_id=1, place_id=3, place=_place(), check_in_at=datetime(2026, 12, 18, 14, tzinfo=timezone.utc),
        check_out_at=datetime(2026, 12, 20, 10, tzinfo=timezone.utc), timezone="Europe/Helsinki", booking_ref=None,
        booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _client(dep_name):
    import app.dependencies as deps
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[getattr(deps, dep_name)] = lambda: service
    return TestClient(app), service


@pytest.fixture
def trips():
    client, service = _client("get_trip_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def legs():
    client, service = _client("get_leg_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def stays():
    client, service = _client("get_stay_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def places():
    client, service = _client("get_place_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def tags():
    client, service = _client("get_travel_tag_service")
    yield client, service
    client.app.dependency_overrides.clear()


class TestAuth:
    @pytest.mark.parametrize("path", ["/travel/trips", "/travel/places", "/travel/tags"])
    def test_requires_a_token(self, trips, path):
        client, _ = trips
        assert client.get(path).status_code in (401, 403)


class TestTrips:
    def test_list_passes_filters(self, trips):
        client, service = trips
        service.get_trips.return_value = [_trip()]
        r = client.get("/travel/trips?status=past&tag=Family&tag=Work&q=ex", headers=AUTH)
        assert r.status_code == 200
        assert r.json()[0]["status"] in ("upcoming", "ongoing", "past")
        filters = service.get_trips.await_args.args[0]
        assert (filters.status, filters.tag, filters.q) == ("past", ["Family", "Work"], "ex")

    def test_list_defaults_to_current(self, trips):
        client, service = trips
        service.get_trips.return_value = []
        client.get("/travel/trips", headers=AUTH)
        assert service.get_trips.await_args.args[0].status == "current"

    def test_unknown_status_is_422(self, trips):
        client, _ = trips
        assert client.get("/travel/trips?status=sometime", headers=AUTH).status_code == 422

    def test_create(self, trips):
        client, service = trips
        service.create_trip.return_value = _trip()
        r = client.post(
            "/travel/trips", headers=AUTH,
            json={"name": "Example trip", "start_date": "2026-12-17", "end_date": "2026-12-24", "tags": ["Family"]},
        )
        assert r.status_code == 201 and r.json()["tags"] == ["Family"]

    def test_create_with_reversed_dates_is_422(self, trips):
        client, _ = trips
        r = client.post("/travel/trips", headers=AUTH, json={"name": "X", "start_date": "2026-12-24", "end_date": "2026-12-17"})
        assert r.status_code == 422

    def test_detail(self, trips):
        client, service = trips
        service.get_trip_detail.return_value = TripDetail(
            **_trip().model_dump(exclude={"status"}), legs=[_leg()], stays=[_stay()], timeline=[], warnings=[]
        )
        r = client.get("/travel/trips/1", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["legs"][0]["departs_local"] == "2026-12-17T06:00:00"
        assert body["stays"][0]["place"]["maps_link"].startswith("https://")

    def test_detail_404(self, trips):
        client, service = trips
        service.get_trip_detail.return_value = None
        assert client.get("/travel/trips/9", headers=AUTH).status_code == 404

    def test_update_value_error_is_422(self, trips):
        client, service = trips
        service.update_trip.side_effect = ValueError("end_date cannot be before start_date")
        r = client.patch("/travel/trips/1", headers=AUTH, json={"start_date": "2027-01-01"})
        assert r.status_code == 422 and "end_date" in r.json()["detail"]

    def test_update_404(self, trips):
        client, service = trips
        service.update_trip.return_value = None
        assert client.patch("/travel/trips/9", headers=AUTH, json={"name": "x"}).status_code == 404

    def test_delete(self, trips):
        client, service = trips
        service.delete_trip.return_value = True
        assert client.delete("/travel/trips/1", headers=AUTH).status_code == 204

    def test_delete_404(self, trips):
        client, service = trips
        service.delete_trip.return_value = False
        assert client.delete("/travel/trips/1", headers=AUTH).status_code == 404


class TestLegs:
    BODY = {
        "trip_id": 1, "mode": "flight", "origin": "A", "destination": "B", "departs_at": "2026-12-17T06:00",
        "arrives_at": "2026-12-17T10:00", "departs_tz": "UTC", "arrives_tz": "Europe/Stockholm",
    }

    def test_create(self, legs):
        client, service = legs
        service.create_leg.return_value = _leg()
        r = client.post("/travel/legs", headers=AUTH, json=self.BODY)
        assert r.status_code == 201
        assert "XX+12" in r.json()["check_flight_url"]

    def test_create_unknown_trip_is_404(self, legs):
        client, service = legs
        service.create_leg.side_effect = TravelNotFoundError("Trip 1 not found")
        assert client.post("/travel/legs", headers=AUTH, json=self.BODY).status_code == 404

    def test_create_bad_zone_is_422(self, legs):
        client, _ = legs
        assert client.post("/travel/legs", headers=AUTH, json={**self.BODY, "departs_tz": "Mars/Base"}).status_code == 422

    def test_update_value_error_is_422(self, legs):
        client, service = legs
        service.update_leg.side_effect = ValueError("arrives_at cannot be before departs_at")
        assert client.patch("/travel/legs/1", headers=AUTH, json={"seat": "1A"}).status_code == 422

    def test_get_404(self, legs):
        client, service = legs
        service.get_leg.return_value = None
        assert client.get("/travel/legs/1", headers=AUTH).status_code == 404

    def test_delete(self, legs):
        client, service = legs
        service.delete_leg.return_value = True
        assert client.delete("/travel/legs/1", headers=AUTH).status_code == 204


class TestStays:
    BODY = {
        "trip_id": 1, "place_id": 3, "check_in_at": "2026-12-18T15:00", "check_out_at": "2026-12-20T11:00",
        "timezone": "Europe/Helsinki",
    }

    def test_create(self, stays):
        client, service = stays
        service.create_stay.return_value = _stay()
        r = client.post("/travel/stays", headers=AUTH, json=self.BODY)
        assert r.status_code == 201 and r.json()["place"]["name"] == "Hotel Example"

    def test_create_unknown_place_is_404(self, stays):
        client, service = stays
        service.create_stay.side_effect = TravelNotFoundError("Place 3 not found")
        assert client.post("/travel/stays", headers=AUTH, json=self.BODY).status_code == 404

    def test_create_grade_out_of_range_is_422(self, stays):
        client, _ = stays
        assert client.post("/travel/stays", headers=AUTH, json={**self.BODY, "grade": 9}).status_code == 422

    def test_update_value_error_is_422(self, stays):
        client, service = stays
        service.update_stay.side_effect = ValueError("check_out_at cannot be before check_in_at")
        assert client.patch("/travel/stays/7", headers=AUTH, json={"notes": "x"}).status_code == 422

    def test_update_404(self, stays):
        client, service = stays
        service.update_stay.return_value = None
        assert client.patch("/travel/stays/7", headers=AUTH, json={"notes": "x"}).status_code == 404

    def test_delete_404(self, stays):
        client, service = stays
        service.delete_stay.return_value = False
        assert client.delete("/travel/stays/7", headers=AUTH).status_code == 404


class TestPlaces:
    def test_create(self, places):
        client, service = places
        service.create_place.return_value = _place()
        r = client.post("/travel/places", headers=AUTH, json={"kind": "hotel", "name": "Hotel Example", "city": "Lisbon"})
        assert r.status_code == 201

    def test_create_unknown_kind_is_422(self, places):
        client, _ = places
        assert client.post("/travel/places", headers=AUTH, json={"kind": "spaceship", "name": "X"}).status_code == 422

    def test_list_filters(self, places):
        client, service = places
        service.get_places.return_value = [_place()]
        client.get("/travel/places?kind=hotel&city=Lisbon&q=ex", headers=AUTH)
        filters = service.get_places.await_args.args[0]
        assert (filters.kind, filters.city, filters.q) == ("hotel", "Lisbon", "ex")

    def test_get_404(self, places):
        client, service = places
        service.get_place_detail.return_value = None
        assert client.get("/travel/places/3", headers=AUTH).status_code == 404

    def test_update_null_name_is_422(self, places):
        client, service = places
        service.update_place.side_effect = ValueError("name cannot be null")
        assert client.patch("/travel/places/3", headers=AUTH, json={"name": None}).status_code == 422

    def test_delete_in_use_is_409(self, places):
        client, service = places
        service.delete_place.side_effect = PlaceInUseError(3)
        assert client.delete("/travel/places/3", headers=AUTH).status_code == 409

    def test_delete(self, places):
        client, service = places
        service.delete_place.return_value = True
        assert client.delete("/travel/places/3", headers=AUTH).status_code == 204


class TestTags:
    def test_list(self, tags):
        client, service = tags
        service.get_tags.return_value = [TravelTagUsage(id=1, name="Family", trip_count=2)]
        assert client.get("/travel/tags", headers=AUTH).json() == [{"id": 1, "name": "Family", "trip_count": 2, "place_count": 0}]

    def test_rename_clash_is_409(self, tags):
        client, service = tags
        service.rename_tag.side_effect = TravelTagNameTakenError("x")
        assert client.patch("/travel/tags/1", headers=AUTH, json={"name": "x"}).status_code == 409

    def test_rename(self, tags):
        client, service = tags
        service.rename_tag.return_value = TravelTagRead(id=1, name="Work")
        assert client.patch("/travel/tags/1", headers=AUTH, json={"name": "Work"}).json()["name"] == "Work"

    def test_delete_404(self, tags):
        client, service = tags
        service.delete_tag.return_value = False
        assert client.delete("/travel/tags/1", headers=AUTH).status_code == 404


def _visit(id=11, status="planned", grade=None) -> VisitRead:
    return VisitRead(
        id=id, place_id=3, place=VisitPlace(id=3, kind="restaurant", name="Cafe Example", city="Lisbon", maps_url=None, lat=None, lng=None),
        trip_id=1, trip_name="Example trip", status=status, visit_date=date(2026, 12, 18), visit_time=time(20, 0),
        notes=None, grade=grade, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def visits():
    client, service = _client("get_visit_service")
    yield client, service
    client.app.dependency_overrides.clear()


class TestVisits:
    def test_create_defaults_to_planned(self, visits):
        client, service = visits
        service.create_visit.return_value = _visit()
        r = client.post("/travel/visits", headers=AUTH, json={"place_id": 3, "trip_id": 1, "visit_date": "2026-12-18", "visit_time": "20:00"})
        assert r.status_code == 201
        assert service.create_visit.await_args.args[0].status == "planned"
        assert r.json()["place"]["maps_link"].startswith("https://")

    def test_grading_a_planned_visit_is_422(self, visits):
        client, _ = visits
        assert client.post("/travel/visits", headers=AUTH, json={"place_id": 3, "grade": 4}).status_code == 422

    def test_unknown_status_is_422(self, visits):
        client, _ = visits
        assert client.post("/travel/visits", headers=AUTH, json={"place_id": 3, "status": "maybe"}).status_code == 422

    def test_create_with_unknown_place_is_404(self, visits):
        client, service = visits
        service.create_visit.side_effect = TravelNotFoundError("Place 3 not found")
        assert client.post("/travel/visits", headers=AUTH, json={"place_id": 3}).status_code == 404

    def test_list_filters(self, visits):
        client, service = visits
        service.get_visits.return_value = [_visit()]
        client.get("/travel/visits?trip_id=1&status=planned&no_trip=false&place_id=3", headers=AUTH)
        filters = service.get_visits.await_args.args[0]
        assert (filters.trip_id, filters.status, filters.place_id, filters.no_trip) == (1, "planned", 3, False)

    def test_update_value_error_is_422(self, visits):
        client, service = visits
        service.update_visit.side_effect = ValueError("Only a visited visit can be graded")
        assert client.patch("/travel/visits/11", headers=AUTH, json={"grade": 4}).status_code == 422

    def test_update_404(self, visits):
        client, service = visits
        service.update_visit.return_value = None
        assert client.patch("/travel/visits/11", headers=AUTH, json={"notes": "x"}).status_code == 404

    def test_get_and_delete(self, visits):
        client, service = visits
        service.get_visit.return_value = _visit()
        assert client.get("/travel/visits/11", headers=AUTH).json()["trip_name"] == "Example trip"
        service.delete_visit.return_value = False
        assert client.delete("/travel/visits/11", headers=AUTH).status_code == 404


class TestPlaceDetailAndFilters:
    def test_place_detail_returns_history_and_derived_grade(self, places):
        client, service = places
        service.get_place_detail.return_value = PlaceDetail(
            **_place().model_dump(), visits=[_visit(status="visited", grade=4)], stays=[_stay()],
        )
        body = client.get("/travel/places/3", headers=AUTH).json()
        assert body["visits"][0]["grade"] == 4 and body["stays"][0]["id"] == 7
        assert body["tags"] == [] and body["grade"] is None

    def test_list_passes_the_new_filters(self, places):
        client, service = places
        service.get_places.return_value = []
        client.get("/travel/places?tag=Would+return&tag=Family&min_grade=4&status=visited&no_trip=true", headers=AUTH)
        f = service.get_places.await_args.args[0]
        assert (f.tag, f.min_grade, f.status, f.no_trip) == (["Would return", "Family"], 4, "visited", True)

    def test_min_grade_out_of_range_is_422(self, places):
        client, _ = places
        assert client.get("/travel/places?min_grade=9", headers=AUTH).status_code == 422

    def test_create_with_tags(self, places):
        client, service = places
        service.create_place.return_value = _place()
        client.post("/travel/places", headers=AUTH, json={"kind": "cafe", "name": "X", "tags": [" Would return", "would return"]})
        assert service.create_place.await_args.args[0].tags == ["Would return"]


class TestTripDetailVisits:
    def test_all_visits_flag_is_forwarded(self, trips):
        client, service = trips
        service.get_trip_detail.return_value = TripDetail(
            **_trip().model_dump(exclude={"status"}), legs=[], stays=[], timeline=[], warnings=[],
            visits=[_visit()], hidden_visit_count=2,
        )
        body = client.get("/travel/trips/1?all_visits=true", headers=AUTH).json()
        assert service.get_trip_detail.await_args.kwargs == {"include_all_visits": True}
        assert body["visits"][0]["id"] == 11 and body["hidden_visit_count"] == 2


from decimal import Decimal  # noqa: E402

from app.features.travel.calendar_import.schemas import CalendarCandidate  # noqa: E402
from app.features.travel.errors import TravelConflictError  # noqa: E402
from app.features.travel.transaction_links.schemas import (  # noqa: E402
    ApplyDefaultTagsResult,
    Cost,
    EntityCost,
    KindCost,
    LinkedTransaction,
    LinkedTransactions,
    PlaceCosts,
    TripCosts,
)
from app.features.travel.transaction_links.service import TransferNotLinkableError  # noqa: E402


def _linked() -> LinkedTransactions:
    return LinkedTransactions(
        transactions=[LinkedTransaction(
            id=9, date=datetime(2026, 12, 18), merchant="M", description=None, type="expense",
            amount=Decimal("10.00"), currency="EUR", amount_eur=Decimal("10.00"),
        )],
        cost=Cost(total_eur=Decimal("10.00"), transaction_count=1),
    )


@pytest.fixture
def link_service():
    client, service = _client("get_transaction_link_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def tag_service():
    client, service = _client("get_trip_default_tag_service")
    yield client, service
    client.app.dependency_overrides.clear()


@pytest.fixture
def calendar_service():
    client, service = _client("get_calendar_import_service")
    yield client, service
    client.app.dependency_overrides.clear()


class TestTransactionLinks:
    @pytest.mark.parametrize("kind", ["legs", "stays", "visits"])
    def test_link_and_list(self, link_service, kind):
        client, service = link_service
        service.link.return_value = _linked()
        service.get_linked.return_value = _linked()
        r = client.post(f"/travel/{kind}/4/transactions", headers=AUTH, json={"transaction_id": 9})
        assert r.status_code == 200 and r.json()["cost"]["total_eur"] == "10.00"
        service.link.assert_awaited_once_with(kind, 4, 9)
        assert client.get(f"/travel/{kind}/4/transactions", headers=AUTH).json()["transactions"][0]["id"] == 9

    def test_unknown_kind_is_422(self, link_service):
        client, _ = link_service
        assert client.get("/travel/trips/4/transactions", headers=AUTH).status_code == 422

    def test_link_unknown_target_is_404(self, link_service):
        client, service = link_service
        service.link.side_effect = TravelNotFoundError("Transaction 9 not found")
        assert client.post("/travel/legs/4/transactions", headers=AUTH, json={"transaction_id": 9}).status_code == 404

    def test_linking_a_transfer_is_422(self, link_service):
        client, service = link_service
        service.link.side_effect = TransferNotLinkableError("Transfers can't be linked to a trip")
        r = client.post("/travel/legs/4/transactions", headers=AUTH, json={"transaction_id": 9})
        assert r.status_code == 422 and "Transfers" in r.json()["detail"]

    def test_unlink(self, link_service):
        client, service = link_service
        service.unlink.return_value = True
        assert client.delete("/travel/stays/4/transactions/9", headers=AUTH).status_code == 204
        service.unlink.return_value = False
        assert client.delete("/travel/stays/4/transactions/9", headers=AUTH).status_code == 404


class TestCostsAndDefaultTags:
    def test_trip_costs(self, link_service):
        client, service = link_service
        service.get_trip_costs.return_value = TripCosts(
            total=Cost(total_eur=Decimal("250.00"), transaction_count=3, unconverted_count=1),
            by_kind=[KindCost(kind="flight", total_eur=Decimal("120.00"), transaction_count=1)],
            legs=[EntityCost(id=1, total_eur=Decimal("120.00"), transaction_count=1)], stays=[], visits=[],
        )
        body = client.get("/travel/trips/1/costs", headers=AUTH).json()
        assert body["total"]["unconverted_count"] == 1 and body["by_kind"][0]["kind"] == "flight"

    def test_trip_costs_404(self, link_service):
        client, service = link_service
        service.get_trip_costs.return_value = None
        assert client.get("/travel/trips/1/costs", headers=AUTH).status_code == 404

    def test_place_costs(self, link_service):
        client, service = link_service
        service.get_place_costs.return_value = PlaceCosts(total=Cost(total_eur=Decimal("80.00"), transaction_count=2))
        assert client.get("/travel/places/3/costs", headers=AUTH).json()["total"]["transaction_count"] == 2
        service.get_place_costs.return_value = None
        assert client.get("/travel/places/3/costs", headers=AUTH).status_code == 404

    def test_apply_default_tags(self, tag_service):
        client, service = tag_service
        service.apply_to_existing.return_value = (["Travel", "Hotel"], 5)
        r = client.post("/travel/trips/1/apply-default-tags", headers=AUTH)
        assert r.json() == ApplyDefaultTagsResult(tags=["Travel", "Hotel"], added=5).model_dump()

    def test_apply_default_tags_unknown_trip(self, tag_service):
        client, service = tag_service
        service.apply_to_existing.side_effect = TravelNotFoundError("Trip 9 not found")
        assert client.post("/travel/trips/9/apply-default-tags", headers=AUTH).status_code == 404


class TestCalendarImport:
    def test_lists_candidates(self, calendar_service):
        client, service = calendar_service
        service.get_candidates.return_value = [CalendarCandidate(
            event_id=1, title="Flight XX 12", location=None, description=None, all_day=False, timezone="UTC",
            start_local=datetime(2026, 12, 17, 6), end_local=datetime(2026, 12, 17, 9), imported_as="leg", imported_id=4,
        )]
        body = client.get("/travel/trips/1/calendar-events", headers=AUTH).json()
        assert body[0]["imported_as"] == "leg" and body[0]["start_local"] == "2026-12-17T06:00:00"

    def test_unknown_trip(self, calendar_service):
        client, service = calendar_service
        service.get_candidates.return_value = None
        assert client.get("/travel/trips/1/calendar-events", headers=AUTH).status_code == 404

    def test_importing_the_same_event_twice_is_409(self, legs):
        client, service = legs
        service.create_leg.side_effect = TravelConflictError("That calendar event is already imported as a leg")
        r = client.post("/travel/legs", headers=AUTH, json={
            "trip_id": 1, "mode": "flight", "origin": "A", "destination": "B", "departs_at": "2026-12-17T06:00",
            "arrives_at": "2026-12-17T10:00", "departs_tz": "UTC", "arrives_tz": "UTC", "calendar_event_id": 5,
        })
        assert r.status_code == 409

    def test_stay_import_conflict_is_409(self, stays):
        client, service = stays
        service.create_stay.side_effect = TravelConflictError("already imported")
        r = client.post("/travel/stays", headers=AUTH, json={
            "place_id": 3, "check_in_at": "2026-12-18T15:00", "check_out_at": "2026-12-19T11:00", "timezone": "UTC",
            "calendar_event_id": 5,
        })
        assert r.status_code == 409


class TestTripMap:
    def test_returns_the_points(self, trips):
        from app.features.travel.trips.map_points import MapPoint, TripMap

        client, service = trips
        service.get_trip_map.return_value = TripMap(
            trip_id=1, name="Trip", points=[MapPoint(name="OPO airport", address="OPO airport", category="airport")]
        )
        resp = client.get("/travel/trips/1/map", headers=AUTH)
        assert resp.status_code == 200 and resp.json()["points"][0]["name"] == "OPO airport"

    def test_scope_is_passed_on_and_validated(self, trips):
        from app.features.travel.trips.map_points import TripMap

        client, service = trips
        service.get_trip_map.return_value = TripMap(trip_id=1, name="Trip", points=[])
        assert client.get("/travel/trips/1/map?scope=visited", headers=AUTH).status_code == 200
        service.get_trip_map.assert_awaited_with(1, "visited")
        for scope in ("planned", "missed"):
            assert client.get(f"/travel/trips/1/map?scope={scope}", headers=AUTH).status_code == 200
        assert client.get("/travel/trips/1/map?scope=bogus", headers=AUTH).status_code == 422

    def test_unknown_trip_is_404(self, trips):
        client, service = trips
        service.get_trip_map.return_value = None
        assert client.get("/travel/trips/9/map", headers=AUTH).status_code == 404


def test_trip_today_is_404_for_an_unknown_trip():
    client, service = _client("get_trip_service")
    service.get_today.return_value = None
    assert client.get("/travel/trips/9/today", headers=AUTH).status_code == 404


def test_other_events_404_for_an_unknown_trip():
    client, service = _client("get_trip_snooze_service")
    service.get_other_events.return_value = None
    assert client.get("/travel/trips/9/other-events", headers=AUTH).status_code == 404


def test_forecast_404_for_an_unknown_trip():
    client, service = _client("get_trip_forecast_service")
    service.get_forecast.return_value = None
    assert client.get("/travel/trips/9/forecast", headers=AUTH).status_code == 404


def test_while_away_404_for_an_unknown_trip():
    client, service = _client("get_while_away_service")
    service.get_while_away.return_value = None
    assert client.get("/travel/trips/9/while-away", headers=AUTH).status_code == 404


def test_unlinked_transactions_404_for_an_unknown_trip():
    client, service = _client("get_transaction_link_service")
    service.get_unlinked.return_value = None
    assert client.get("/travel/trips/9/unlinked-transactions", headers=AUTH).status_code == 404


def test_move_visits_routes_to_the_service_and_maps_not_found():
    from app.features.travel.errors import TravelNotFoundError
    from app.features.travel.visits.schemas import VisitMoveResult

    client, service = _client("get_visit_service")
    service.move_visits.return_value = VisitMoveResult(moved=[1], failed=[])
    body = {"from_date": "2026-12-18", "to_date": "2026-12-20", "only_tag": "Outdoor"}
    resp = client.post("/travel/trips/1/visits/move", headers=AUTH, json=body)
    assert resp.status_code == 200 and resp.json() == {"moved": [1], "failed": []}
    service.move_visits.side_effect = TravelNotFoundError("Trip 1 not found")
    assert client.post("/travel/trips/1/visits/move", headers=AUTH, json=body).status_code == 404


@pytest.mark.parametrize("dep,path,method", [("get_leg_service", "/travel/legs/1", "update_leg"), ("get_stay_service", "/travel/stays/1", "update_stay")])
def test_linking_an_event_maps_conflict_and_not_found_on_update(dep, path, method):
    from app.features.travel.errors import TravelConflictError, TravelNotFoundError

    client, service = _client(dep)
    getattr(service, method).side_effect = TravelConflictError("taken")
    assert client.patch(path, headers=AUTH, json={"calendar_event_id": 7}).status_code == 409
    getattr(service, method).side_effect = TravelNotFoundError("Calendar event 7 not found")
    assert client.patch(path, headers=AUTH, json={"calendar_event_id": 7}).status_code == 404


def test_visit_event_action_maps_reason_and_not_found():
    client, service = _client("get_visit_service")
    service.event_action.side_effect = ValueError("The visit already has a calendar event")
    assert client.post("/travel/visits/1/event", headers=AUTH, json={"action": "create"}).status_code == 422
    service.event_action.side_effect = None
    service.event_action.return_value = None
    assert client.post("/travel/visits/1/event", headers=AUTH, json={"action": "create"}).status_code == 404
    assert client.post("/travel/visits/1/event", headers=AUTH, json={"action": "explode"}).status_code == 422
