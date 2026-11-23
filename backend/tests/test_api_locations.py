from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.locations.errors import LocationConflictError, LocationValidationError
from app.features.organizer.locations.schemas import (
    LocationRef,
    LocationTravelTimeRead,
    LocationCategory,
    LocationFilters,
    LocationRead,
    LocationToday,
)

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _read(**kwargs):
    defaults = dict(
        id=1, name="Market", kind="supermarket", address=None, maps_url=None,
        opening_hours={"mon": [["08:00", "20:00"]]}, opening_hours_text="mon 08:00-20:00", notes=None, active=True,
        categories=[LocationCategory(id=1, name="groceries")],
        today=LocationToday(date=date(2026, 11, 23), hours="08:00-20:00", open_now=True),
        created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(kwargs)
    return LocationRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.list.return_value = [_read()]
    svc.get.return_value = _read()
    svc.create.return_value = _read(id=2)
    svc.update.return_value = _read(notes="Cash only")
    svc.delete.return_value = True
    svc.get_categories.return_value = [LocationCategory(id=1, name="groceries")]
    svc.set_categories.return_value = [LocationCategory(id=3, name="pharmacy")]
    return svc


def _route(**kwargs):
    defaults = dict(
        id=5, origin=LocationRef(id=1, name="Home", kind="home"), destination=LocationRef(id=2, name="Market", kind="supermarket"),
        mode="foot", minutes=12, created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(kwargs)
    return LocationTravelTimeRead(**defaults)


@pytest.fixture
def mock_travel_times():
    svc = AsyncMock()
    svc.list_for.return_value = [_route()]
    svc.set.return_value = _route(minutes=10)
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service, mock_travel_times):
    from app.main import app
    from app.dependencies import get_location_service, get_location_travel_time_service
    app.dependency_overrides[get_location_service] = lambda: mock_service
    app.dependency_overrides[get_location_travel_time_service] = lambda: mock_travel_times
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestList:
    def test_returns_locations_with_today(self, client):
        response = client.get("/organizer/locations", headers=AUTH)

        assert response.status_code == 200
        body = response.json()[0]
        assert body["today"]["open_now"] is True
        assert body["categories"] == [{"id": 1, "name": "groceries"}]
        assert body["opening_hours_text"] == "mon 08:00-20:00"

    def test_filters_are_passed(self, client, mock_service):
        client.get("/organizer/locations?kind=Supermarket&active=true&category_id=4", headers=AUTH)

        assert mock_service.list.call_args.args[0] == LocationFilters(kind="supermarket", active=True, category_id=4)

    def test_requires_auth(self, client):
        assert client.get("/organizer/locations").status_code == 403


class TestGetCreateUpdateDelete:
    def test_get_404(self, client, mock_service):
        mock_service.get.return_value = None
        assert client.get("/organizer/locations/9", headers=AUTH).status_code == 404

    def test_create_accepts_text_hours(self, client, mock_service):
        response = client.post(
            "/organizer/locations", headers=AUTH,
            json={"name": "Market", "kind": "supermarket", "opening_hours": "mon 8-20", "category_ids": [1]},
        )

        assert response.status_code == 201
        payload = mock_service.create.call_args.args[0]
        assert payload.opening_hours == "mon 8-20"
        assert payload.category_ids == [1]

    def test_create_blank_name_is_422(self, client):
        assert client.post("/organizer/locations", headers=AUTH, json={"name": " "}).status_code == 422

    def test_conflict_is_409_with_message(self, client, mock_service):
        mock_service.create.side_effect = LocationConflictError("Home is already set: 'Home' (id 1)")

        response = client.post("/organizer/locations", headers=AUTH, json={"name": "Flat", "kind": "home"})

        assert response.status_code == 409
        assert response.json()["detail"] == "Home is already set: 'Home' (id 1)"

    def test_bad_hours_are_422_with_a_text_detail(self, client, mock_service):
        mock_service.create.side_effect = LocationValidationError("Opening hours: 'funday' is not a day")

        response = client.post("/organizer/locations", headers=AUTH, json={"name": "Market", "opening_hours": "funday 9"})

        assert response.status_code == 422
        assert response.json()["detail"] == "Opening hours: 'funday' is not a day"

    def test_update_only_sends_given_fields(self, client, mock_service):
        response = client.patch("/organizer/locations/1", headers=AUTH, json={"notes": "Cash only"})

        assert response.status_code == 200
        assert mock_service.update.call_args.args[1].model_dump(exclude_unset=True) == {"notes": "Cash only"}

    def test_update_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/organizer/locations/9", headers=AUTH, json={"notes": "x"}).status_code == 404

    def test_delete(self, client, mock_service):
        assert client.delete("/organizer/locations/1", headers=AUTH).status_code == 204
        mock_service.delete.return_value = False
        assert client.delete("/organizer/locations/1", headers=AUTH).status_code == 404


class TestCategories:
    def test_get(self, client):
        response = client.get("/organizer/locations/1/categories", headers=AUTH)

        assert response.json() == [{"id": 1, "name": "groceries"}]

    def test_put_replaces(self, client, mock_service):
        response = client.put("/organizer/locations/1/categories", headers=AUTH, json={"category_ids": [3]})

        assert response.status_code == 200
        mock_service.set_categories.assert_awaited_once_with(1, [3])

    def test_404(self, client, mock_service):
        mock_service.get_categories.return_value = None
        mock_service.set_categories.return_value = None

        assert client.get("/organizer/locations/9/categories", headers=AUTH).status_code == 404
        assert client.put("/organizer/locations/9/categories", headers=AUTH, json={"category_ids": []}).status_code == 404


class TestTravelTimes:
    def test_list(self, client, mock_travel_times):
        response = client.get("/organizer/locations/2/travel-times", headers=AUTH)

        assert response.status_code == 200
        body = response.json()[0]
        assert (body["origin"]["name"], body["destination"]["name"], body["mode"], body["minutes"]) == ("Home", "Market", "foot", 12)
        mock_travel_times.list_for.assert_awaited_once_with(2)

    def test_put_sets_the_route(self, client, mock_travel_times):
        response = client.put(
            "/organizer/locations/1/travel-times", headers=AUTH, json={"destination_id": 2, "mode": "Foot", "minutes": 10}
        )

        assert response.status_code == 200 and response.json()["minutes"] == 10
        origin_id, payload = mock_travel_times.set.call_args.args
        assert (origin_id, payload.destination_id, payload.mode, payload.minutes) == (1, 2, "foot", 10)

    def test_put_bad_minutes_is_422(self, client):
        response = client.put("/organizer/locations/1/travel-times", headers=AUTH, json={"destination_id": 2, "mode": "foot", "minutes": 0})
        assert response.status_code == 422

    def test_validation_error_from_the_service_is_422_text(self, client, mock_travel_times):
        mock_travel_times.set.side_effect = LocationValidationError("Unknown location id 9")

        response = client.put("/organizer/locations/1/travel-times", headers=AUTH, json={"destination_id": 9, "mode": "foot", "minutes": 5})

        assert response.status_code == 422 and response.json()["detail"] == "Unknown location id 9"

    def test_unknown_location_is_404(self, client, mock_travel_times):
        mock_travel_times.list_for.return_value = None
        mock_travel_times.set.return_value = None

        assert client.get("/organizer/locations/9/travel-times", headers=AUTH).status_code == 404
        assert client.put("/organizer/locations/9/travel-times", headers=AUTH, json={"destination_id": 2, "mode": "foot", "minutes": 5}).status_code == 404

    def test_delete(self, client, mock_travel_times):
        assert client.delete("/organizer/locations/travel-times/5", headers=AUTH).status_code == 204
        mock_travel_times.delete.assert_awaited_once_with(5)
        mock_travel_times.delete.return_value = False
        assert client.delete("/organizer/locations/travel-times/5", headers=AUTH).status_code == 404
