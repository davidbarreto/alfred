from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.location.errors import LocationConflictError, LocationValidationError
from app.features.location.places.schemas import PlaceRef
from app.features.organizer.everyday_places.schemas import EverydayPlaceCreate, PlaceCategory
from app.features.organizer.travel_times.schemas import TravelTimeRead, TravelTimeSet
from place_read_helpers import everyday_read

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _route(**kwargs):
    defaults = dict(
        id=5, origin=PlaceRef(id=1, name="Home", kind="home"), destination=PlaceRef(id=2, name="Market", kind="supermarket"),
        mode="foot", minutes=12, created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(kwargs)
    return TravelTimeRead(**defaults)


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.list.return_value = [everyday_read()]
    svc.get.return_value = everyday_read()
    svc.create.return_value = everyday_read(id=2)
    svc.add.return_value = everyday_read()
    svc.remove.return_value = True
    svc.get_categories.return_value = [PlaceCategory(id=1, name="groceries")]
    svc.set_categories.return_value = [PlaceCategory(id=3, name="pharmacy")]
    return svc


@pytest.fixture
def travel_times():
    svc = AsyncMock()
    svc.list_for.return_value = [_route()]
    svc.set.return_value = _route(minutes=10)
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(service, travel_times):
    from app.dependencies import get_everyday_place_service, get_travel_time_service
    from app.main import app
    app.dependency_overrides[get_everyday_place_service] = lambda: service
    app.dependency_overrides[get_travel_time_service] = lambda: travel_times
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestList:
    def test_returns_everyday_places_with_categories(self, client):
        response = client.get("/organizer/places", headers=AUTH)

        assert response.status_code == 200
        body = response.json()[0]
        assert body["everyday"] is True
        assert body["categories"] == [{"id": 1, "name": "groceries"}]
        assert body["today"]["hours"] == "08:00-20:00"

    def test_passes_the_filters(self, client, service):
        client.get("/organizer/places?kind=supermarket&active=true&category_id=4&q=school", headers=AUTH)

        filters = service.list.call_args.args[0]
        assert (filters.kind, filters.active, filters.category_id, filters.q) == ("supermarket", True, 4, "school")

    def test_requires_auth(self, client):
        assert client.get("/organizer/places").status_code == 403


class TestCreate:
    def test_creates_with_categories(self, client, service):
        response = client.post(
            "/organizer/places", json={"name": "Market", "kind": "supermarket", "category_ids": [1, 2]}, headers=AUTH
        )

        assert response.status_code == 201
        sent: EverydayPlaceCreate = service.create.call_args.args[0]
        assert sent.category_ids == [1, 2]

    def test_validation_error_is_422(self, client, service):
        service.create.side_effect = LocationValidationError("Unknown shopping category ids: [7]")
        assert client.post("/organizer/places", json={"name": "Market"}, headers=AUTH).status_code == 422


class TestMembership:
    def test_get_any_place(self, client, service):
        service.get.return_value = everyday_read(everyday=False)
        assert client.get("/organizer/places/1", headers=AUTH).json()["everyday"] is False
        service.get.return_value = None
        assert client.get("/organizer/places/1", headers=AUTH).status_code == 404

    def test_put_adds(self, client, service):
        assert client.put("/organizer/places/1", headers=AUTH).status_code == 200
        service.add.assert_awaited_once_with(1)
        service.add.return_value = None
        assert client.put("/organizer/places/9", headers=AUTH).status_code == 404

    def test_delete_removes(self, client, service):
        assert client.delete("/organizer/places/1", headers=AUTH).status_code == 204
        service.remove.return_value = False
        assert client.delete("/organizer/places/9", headers=AUTH).status_code == 404

    def test_removing_home_is_409(self, client, service):
        service.remove.side_effect = LocationConflictError("Home is always an everyday place")
        assert client.delete("/organizer/places/1", headers=AUTH).status_code == 409


class TestCategories:
    def test_get_and_put(self, client, service):
        assert client.get("/organizer/places/1/categories", headers=AUTH).json() == [{"id": 1, "name": "groceries"}]
        response = client.put("/organizer/places/1/categories", json={"category_ids": [3]}, headers=AUTH)
        assert response.json() == [{"id": 3, "name": "pharmacy"}]
        service.set_categories.assert_awaited_once_with(1, [3])

    def test_unknown_place_is_404(self, client, service):
        service.get_categories.return_value = None
        service.set_categories.return_value = None
        assert client.get("/organizer/places/9/categories", headers=AUTH).status_code == 404
        assert client.put("/organizer/places/9/categories", json={"category_ids": []}, headers=AUTH).status_code == 404


class TestTravelTimes:
    def test_list_set_delete(self, client, travel_times):
        assert client.get("/organizer/places/2/travel-times", headers=AUTH).json()[0]["mode"] == "foot"

        response = client.put(
            "/organizer/places/1/travel-times", json={"destination_id": 2, "mode": "Foot", "minutes": 10}, headers=AUTH
        )
        assert response.json()["minutes"] == 10
        origin, sent = travel_times.set.call_args.args
        assert origin == 1 and sent == TravelTimeSet(destination_id=2, mode="foot", minutes=10)

        assert client.delete("/organizer/travel-times/5", headers=AUTH).status_code == 204
        travel_times.delete.return_value = False
        assert client.delete("/organizer/travel-times/5", headers=AUTH).status_code == 404

    def test_unknown_place_is_404(self, client, travel_times):
        travel_times.list_for.return_value = None
        travel_times.set.return_value = None
        assert client.get("/organizer/places/9/travel-times", headers=AUTH).status_code == 404
        body = {"destination_id": 2, "mode": "car", "minutes": 5}
        assert client.put("/organizer/places/9/travel-times", json=body, headers=AUTH).status_code == 404
