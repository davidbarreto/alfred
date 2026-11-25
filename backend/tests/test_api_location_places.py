from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.places.schemas import PlaceCreate, PlaceFilters, PlaceUpdate
from place_read_helpers import place_read

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.list.return_value = [place_read()]
    svc.get.return_value = place_read()
    svc.create.return_value = place_read(id=2)
    svc.update.return_value = place_read(notes="Cash only")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(service):
    from app.dependencies import get_place_service
    from app.main import app
    app.dependency_overrides[get_place_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestList:
    def test_returns_places_with_city_today_and_links(self, client):
        response = client.get("/location/places", headers=AUTH)

        assert response.status_code == 200
        body = response.json()[0]
        assert body["city"]["name"] == "Hometown"
        assert body["today"]["open_now"] is True
        assert body["opening_hours_text"] == "mon 08:00-20:00"
        assert body["maps_link"].startswith("https://www.google.com/maps/search/")

    def test_passes_the_filters(self, client, service):
        client.get("/location/places?kind=Work&city_id=15&country_id=1&active=true&q=caf", headers=AUTH)

        filters: PlaceFilters = service.list.call_args.args[0]
        assert (filters.kind, filters.city_id, filters.country_id, filters.active, filters.q) == ("work", 15, 1, True, "caf")

    def test_unknown_kind_is_422(self, client):
        assert client.get("/location/places?kind=castle", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/location/places").status_code == 403


class TestCreate:
    def test_creates(self, client, service):
        response = client.post(
            "/location/places", json={"name": "Market", "kind": "supermarket", "coordinates": "41.1, -8.6"}, headers=AUTH
        )

        assert response.status_code == 201
        sent: PlaceCreate = service.create.call_args.args[0]
        assert sent.coordinates == (41.1, -8.6) and sent.city_id is None

    @pytest.mark.parametrize(
        "error,status", [
            (LocationConflictError("taken"), 409),
            (LocationValidationError("no home"), 422),
            (LocationNotFoundError("City 9 not found"), 404),
        ],
    )
    def test_maps_the_location_errors(self, client, service, error, status):
        service.create.side_effect = error

        response = client.post("/location/places", json={"name": "Market"}, headers=AUTH)

        assert response.status_code == status
        assert response.json()["detail"] == str(error)


class TestOne:
    def test_get_and_404(self, client, service):
        assert client.get("/location/places/1", headers=AUTH).json()["id"] == 1
        service.get.return_value = None
        assert client.get("/location/places/1", headers=AUTH).status_code == 404

    def test_patch_sends_only_what_was_given(self, client, service):
        response = client.patch("/location/places/1", json={"notes": "Cash only", "active": False}, headers=AUTH)

        assert response.status_code == 200
        place_id, sent = service.update.call_args.args
        assert place_id == 1 and isinstance(sent, PlaceUpdate)
        assert sent.model_dump(exclude_unset=True) == {"notes": "Cash only", "active": False}

    def test_patch_unknown_is_404(self, client, service):
        service.update.return_value = None
        assert client.patch("/location/places/9", json={"notes": "x"}, headers=AUTH).status_code == 404

    def test_delete(self, client, service):
        assert client.delete("/location/places/1", headers=AUTH).status_code == 204
        service.delete.return_value = False
        assert client.delete("/location/places/1", headers=AUTH).status_code == 404

    def test_delete_held_place_is_409(self, client, service):
        service.delete.side_effect = LocationConflictError("'Gym' can't be deleted: it has 2 travel time(s)")

        response = client.delete("/location/places/1", headers=AUTH)

        assert response.status_code == 409
        assert "travel time" in response.json()["detail"]
