from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.travel import TravelServices, handle_travel
from app.features.location.countries.schemas import CountryRef
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.links.schemas import WebLinkRead
from app.features.travel.trips.trip_cities import TripCity
from travel_city_helpers import city_ref

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _link(id=5, **kw):
    base = dict(id=id, trip_id=None, place_id=None, city_id=None, country_id=None, url="https://example.com/a", kind="website",
                title="Official", description=None, image_url=None, notes=None, created_at=NOW, updated_at=NOW)
    base.update(kw)
    return WebLinkRead(**base)


def _city_read(name, country, id):
    ref = city_ref(name, country)
    return SimpleNamespace(id=id, name=name, country=ref.country)


@pytest.fixture
def services():
    s = TravelServices(
        trips=AsyncMock(), legs=AsyncMock(), stays=AsyncMock(), places=AsyncMock(), visits=AsyncMock(),
        links=AsyncMock(), default_tags=AsyncMock(), recap=AsyncMock(), web_links=AsyncMock(), cities=AsyncMock(), countries=AsyncMock(),
    )
    s.web_links.create_city_link.return_value = _link(city_id=4)
    s.web_links.get_city_links.return_value = [_link(city_id=4)]
    return s


async def run(command, arguments, services):
    return await handle_travel("travel_link", command, arguments, services)


class TestOwner:
    async def test_a_city_by_id_needs_no_lookup(self, services):
        result = await run("add", {"url": "https://example.com/a", "city": "4"}, services)
        services.web_links.create_city_link.assert_awaited_once()
        assert services.web_links.create_city_link.await_args.args[0] == 4
        assert result["id"] == 5 and result["url"] == "https://example.com/a"
        services.cities.get_cities.assert_not_awaited()

    async def test_a_city_by_name_is_matched_exactly_ignoring_case(self, services):
        services.cities.get_cities.return_value = [_city_read("Alpha", "Examplia", 4), _city_read("Alphabet", "Examplia", 9)]
        await run("add", {"url": "https://example.com/a", "city": "alpha"}, services)
        assert services.web_links.create_city_link.await_args.args[0] == 4

    async def test_a_name_in_several_countries_is_refused_and_lists_them(self, services):
        services.cities.get_cities.return_value = [_city_read("Alpha", "Examplia", 4), _city_read("Alpha", "Otherland", 8)]
        with pytest.raises(HTTPException) as exc:
            await run("add", {"url": "https://example.com/a", "city": "Alpha"}, services)
        assert exc.value.status_code == 400 and "Examplia, Otherland" in exc.value.detail
        services.web_links.create_city_link.assert_not_awaited()

    async def test_the_country_narrows_the_city(self, services):
        services.cities.get_cities.return_value = [_city_read("Alpha", "Examplia", 4), _city_read("Alpha", "Otherland", 8)]
        await run("add", {"url": "https://example.com/a", "city": "Alpha", "country": "otherland"}, services)
        assert services.web_links.create_city_link.await_args.args[0] == 8

    async def test_an_unknown_city_is_a_404(self, services):
        services.cities.get_cities.return_value = []
        with pytest.raises(HTTPException) as exc:
            await run("list", {"city": "Nowhere"}, services)
        assert exc.value.status_code == 404

    async def test_a_country_by_name(self, services):
        services.countries.get_countries.return_value = [CountryRef(id=2, name="Examplia", code=None)]
        services.web_links.create_country_link.return_value = _link(country_id=2)
        await run("add", {"url": "https://example.com/a", "country": "examplia"}, services)
        assert services.web_links.create_country_link.await_args.args[0] == 2

    async def test_a_trip_by_id_and_a_place_by_id(self, services):
        services.trips.get_trip.return_value = SimpleNamespace(id=1)
        services.web_links.create_trip_link.return_value = _link(trip_id=1)
        await run("add", {"url": "https://example.com/a", "trip": "1"}, services)
        assert services.web_links.create_trip_link.await_args.args[0] == 1
        services.places.get_place.return_value = SimpleNamespace(id=3)
        services.web_links.create_place_link.return_value = _link(place_id=3)
        await run("add", {"url": "https://example.com/a", "place": "3"}, services)
        assert services.web_links.create_place_link.await_args.args[0] == 3

    @pytest.mark.parametrize("arguments", [{}, {"trip": "1", "city": "4"}, {"place": "3", "country": "Examplia"}])
    async def test_exactly_one_owner_is_required(self, services, arguments):
        with pytest.raises(HTTPException) as exc:
            await run("list", arguments, services)
        assert exc.value.status_code == 400 and "exactly one" in exc.value.detail


class TestCommands:
    async def test_list(self, services):
        result = await run("list", {"city": "4"}, services)
        assert result == {"count": 1, "links": [{"id": 5, "url": "https://example.com/a", "title": "Official", "kind": "website", "notes": None}]}

    async def test_add_passes_the_optional_fields(self, services):
        await run("add", {"url": "https://example.com/a", "city": "4", "title": "T", "kind": "booking", "notes": "n"}, services)
        data = services.web_links.create_city_link.await_args.args[1]
        assert (data.url, data.title, data.kind, data.notes) == ("https://example.com/a", "T", "booking", "n")

    async def test_a_bad_address_is_a_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"url": "not a url", "city": "4"}, services)
        assert exc.value.status_code == 400

    async def test_a_duplicate_is_a_409(self, services):
        services.web_links.create_city_link.side_effect = TravelConflictError("This link is already saved here")
        with pytest.raises(HTTPException) as exc:
            await run("add", {"url": "https://example.com/a", "city": "4"}, services)
        assert exc.value.status_code == 409

    async def test_update_sends_only_what_was_given_and_blank_clears(self, services):
        services.web_links.update_link.return_value = _link()
        await run("update", {"id": "5", "title": ""}, services)
        data = services.web_links.update_link.await_args.args[1]
        assert data.model_dump(exclude_unset=True) == {"title": None}

    async def test_update_needs_something_to_change_and_an_existing_link(self, services):
        with pytest.raises(HTTPException):
            await run("update", {"id": "5"}, services)
        services.web_links.update_link.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run("update", {"id": "5", "title": "x"}, services)
        assert exc.value.status_code == 404

    async def test_delete(self, services):
        services.web_links.delete_link.return_value = True
        assert "deleted" in (await run("delete", {"id": "5"}, services))["message"]
        services.web_links.delete_link.return_value = False
        with pytest.raises(HTTPException) as exc:
            await run("delete", {"id": "5"}, services)
        assert exc.value.status_code == 404

    async def test_an_unknown_owner_from_the_service_is_a_404(self, services):
        services.web_links.get_city_links.side_effect = TravelNotFoundError("City 4 not found")
        with pytest.raises(HTTPException) as exc:
            await run("list", {"city": "4"}, services)
        assert exc.value.status_code == 404


class TestSuggest:
    async def test_lists_the_home_and_stayed_cities_and_their_countries_with_what_is_saved(self, services):
        services.trips.get_trip.return_value = SimpleNamespace(id=1, name="Example trip")
        alpha, beta, passed = city_ref("Alpha", "Examplia"), city_ref("Beta", "Otherland"), city_ref("Gamma", "Passland")
        services.trips.get_trip_detail.return_value = SimpleNamespace(cities=[
            TripCity(city=alpha, role="home"), TripCity(city=beta, role="stayed"), TripCity(city=passed, role="passed")])
        services.web_links.get_city_links.return_value = [_link(url="https://alpha.example/")]
        services.web_links.get_country_links.return_value = []
        result = await run("suggest", {"trip": "1"}, services)
        assert [c["name"] for c in result["cities"]] == ["Alpha", "Beta"]
        assert result["cities"][0]["saved"] == ["https://alpha.example/"]
        assert sorted(c["name"] for c in result["countries"]) == ["Examplia", "Otherland"]

    async def test_needs_a_trip(self, services):
        with pytest.raises(HTTPException):
            await run("suggest", {}, services)
