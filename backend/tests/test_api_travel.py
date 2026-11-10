from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.places.service import PlaceInUseError
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.schemas import TravelTagRead, TravelTagUsage
from app.features.travel.tags.service import TravelTagNameTakenError
from app.features.travel.trips.schemas import TripDetail, TripRead

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
        service.get_place.return_value = None
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
        assert client.get("/travel/tags", headers=AUTH).json() == [{"id": 1, "name": "Family", "trip_count": 2}]

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
