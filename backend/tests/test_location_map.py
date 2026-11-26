"""The Places map endpoint: filters, the home city, only rows with coordinates (DB mocked)."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app import dependencies as deps
from app.features.location.errors import LocationNotFoundError
from app.features.location.map.repository import MapRepository
from app.features.location.map.schemas import MapFilters, PlacesMap
from app.features.location.map.service import MapService
from app.main import app

AUTH = {"Authorization": "Bearer test-api-token"}


def _repo(country_of_city=2, country_exists=True, home_city_id=4):
    repo = AsyncMock()
    repo.city_country_id.return_value = country_of_city
    repo.country_exists.return_value = country_exists
    repo.home_city_id.return_value = home_city_id
    repo.countries.return_value = [
        {"id": 2, "name": "Examplia", "code": "EX", "city_count": 2},
        {"id": 3, "name": "Nocodia", "code": None, "city_count": 0},
    ]
    repo.cities.return_value = [
        {"id": 4, "name": "Alpha", "country_id": 2, "latitude": Decimal("38.7"), "longitude": Decimal("-9.1")},
        {"id": 5, "name": "Beta", "country_id": 2, "latitude": Decimal("41.1"), "longitude": Decimal("-8.6")},
    ]
    repo.places.return_value = [
        {"id": 9, "name": "Cafe Example", "kind": "cafe", "city_id": 4, "city_name": "Alpha",
         "latitude": Decimal("38.71"), "longitude": Decimal("-9.14"), "maps_url": None},
    ]
    repo.cities_without_coordinates.return_value = 1
    repo.places_without_coordinates.return_value = 3
    return repo


async def test_world_map_marks_home_city_and_builds_maps_links():
    repo = _repo()
    result = await MapService(repo).get_map(MapFilters())
    assert [c.home for c in result.cities] == [True, False]
    assert result.cities[0].latitude == 38.7
    assert result.places[0].maps_link.startswith("https://www.google.com/maps/search/")
    assert "38.71" in result.places[0].maps_link
    assert (result.cities_without_coordinates, result.places_without_coordinates) == (1, 3)
    repo.countries.assert_awaited_once_with(None)
    repo.places.assert_awaited_once_with(None, None)


async def test_city_map_scopes_to_the_city_and_draws_its_country():
    repo = _repo()
    await MapService(repo).get_map(MapFilters(city_id=4))
    repo.countries.assert_awaited_once_with(2)
    repo.cities.assert_awaited_once_with(2, 4)
    repo.places.assert_awaited_once_with(2, 4)


async def test_country_map_scopes_to_the_country():
    repo = _repo()
    await MapService(repo).get_map(MapFilters(country_id=2))
    repo.countries.assert_awaited_once_with(2)
    repo.places.assert_awaited_once_with(2, None)


async def test_unknown_city_or_country_is_not_found():
    with pytest.raises(LocationNotFoundError):
        await MapService(_repo(country_of_city=None)).get_map(MapFilters(city_id=99))
    with pytest.raises(LocationNotFoundError):
        await MapService(_repo(country_exists=False)).get_map(MapFilters(country_id=99))


def _compiled(session: MagicMock) -> str:
    stmt = session.execute.await_args.args[0]
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.fixture
def session():
    session = MagicMock()
    session.execute = AsyncMock(return_value=[])
    return session


async def test_places_query_keeps_active_places_with_coordinates_in_scope(session):
    await MapRepository(session).places(2, None)
    sql = _compiled(session)
    assert "location.places.latitude IS NOT NULL" in sql
    assert "location.places.active IS true" in sql
    assert "location.cities.country_id = 2" in sql


async def test_cities_query_keeps_cities_with_coordinates_and_city_wins_over_country(session):
    await MapRepository(session).cities(2, 4)
    sql = _compiled(session)
    assert "location.cities.latitude IS NOT NULL" in sql
    assert "location.cities.id = 4" in sql
    assert "country_id = 2" not in sql


async def test_countries_query_counts_cities_and_filters(session):
    await MapRepository(session).countries(2)
    sql = _compiled(session)
    assert "count(location.cities.id)" in sql
    assert "LEFT OUTER JOIN location.cities" in sql
    assert "location.countries.id = 2" in sql


@pytest.fixture
def client():
    service = AsyncMock()
    service.get_map.return_value = PlacesMap(
        countries=[], cities=[], places=[], cities_without_coordinates=0, places_without_coordinates=0,
    )
    app.dependency_overrides[deps.get_map_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.pop(deps.get_map_service, None)


def test_route_passes_filters(client):
    test_client, service = client
    response = test_client.get("/location/map", params={"city_id": 4}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["places"] == []
    assert service.get_map.await_args.args[0].city_id == 4


def test_route_rejects_both_filters(client):
    test_client, _ = client
    response = test_client.get("/location/map", params={"city_id": 4, "country_id": 2}, headers=AUTH)
    assert response.status_code == 422


def test_route_maps_not_found_to_404(client):
    test_client, service = client
    service.get_map.side_effect = LocationNotFoundError("City 99 not found")
    response = test_client.get("/location/map", params={"city_id": 99}, headers=AUTH)
    assert response.status_code == 404
