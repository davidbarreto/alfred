from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.location import handle_location
from app.assistant.commands.resolver import _parse_tokens, _resolve_fragment
from app.features.location.errors import LocationConflictError, LocationValidationError
from app.features.organizer.everyday_places.schemas import EverydayPlaceFilters
from place_read_helpers import everyday_read

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _read(**kwargs):
    return everyday_read(**{"opening_hours": None, "today": None, "categories": [], **kwargs})


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.create.return_value = _read()
    svc.update.return_value = _read()
    svc.find.return_value = _read()
    svc.list.return_value = [_read()]
    svc.category_ids_for.return_value = [1, 2]
    return svc


@pytest.fixture
def travel_times():
    tts = AsyncMock()
    tts.list_for.return_value = []
    tts.find_place.side_effect = lambda name: SimpleNamespace(id={"home": 10, "office": 11}[name]) if name in ("home", "office") else None
    return tts


class TestAdd:
    async def test_builds_the_location_with_categories(self, service, travel_times):
        result = await handle_location("add", {
            "name": "Market by school", "kind": "Supermarket", "opening_hours": "mon-fri 8-20", "sells": "groceries, bakery",
        }, service, travel_times)

        payload = service.create.call_args.args[0]
        assert payload.name == "Market by school"
        assert payload.kind == "supermarket"
        assert payload.opening_hours == "mon-fri 8-20"
        assert payload.category_ids == [1, 2]
        service.category_ids_for.assert_awaited_once_with(["groceries", "bakery"])
        assert result["id"] == 1

    async def test_kind_defaults_to_other(self, service, travel_times):
        await handle_location("add", {"name": "Post office"}, service, travel_times)

        assert service.create.call_args.args[0].kind == "other"

    async def test_unknown_kind_is_400_listing_the_kinds(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Head office", "kind": "office"}, service, travel_times)
        assert exc.value.status_code == 400 and "'work'" in exc.value.detail
        service.create.assert_not_called()

    async def test_name_required(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": " "}, service, travel_times)
        assert exc.value.status_code == 400

    async def test_conflict_is_409(self, service, travel_times):
        service.create.side_effect = LocationConflictError("Home is already set")

        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Flat", "kind": "home"}, service, travel_times)
        assert exc.value.status_code == 409

    async def test_bad_hours_are_422(self, service, travel_times):
        service.create.side_effect = LocationValidationError("Opening hours: bad")

        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Market", "opening_hours": "x"}, service, travel_times)
        assert exc.value.status_code == 422


class TestList:
    async def test_active_only_by_default(self, service, travel_times):
        await handle_location("list", {}, service, travel_times)

        assert service.list.call_args.args[0] == EverydayPlaceFilters(active=True)

    async def test_all_kind_and_sells(self, service, travel_times):
        service.category_ids_for.return_value = [4]

        await handle_location("list", {"all": "yes", "kind": "Pharmacy", "sells": "pharmacy"}, service, travel_times)

        assert service.list.call_args.args[0] == EverydayPlaceFilters(kind="pharmacy", active=None, category_id=4)


    async def test_unknown_kind_filter_is_422(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("list", {"kind": "office"}, service, travel_times)
        assert exc.value.status_code == 422 and "work" in exc.value.detail
        service.list.assert_not_called()


class TestShowUpdateDelete:
    async def test_show_by_name(self, service, travel_times):
        result = await handle_location("show", {"location": "market"}, service, travel_times)

        service.find.assert_awaited_once_with("market")
        assert result["name"] == "Market"

    async def test_unknown_location_is_404(self, service, travel_times):
        service.find.return_value = None

        with pytest.raises(HTTPException) as exc:
            await handle_location("show", {"location": "nowhere"}, service, travel_times)
        assert exc.value.status_code == 404

    async def test_update_clears_an_empty_field_and_archives(self, service, travel_times):
        await handle_location("update", {"location": "Market", "address": "", "active": "false"}, service, travel_times)

        location_id, payload, category_ids = service.update.call_args.args
        assert location_id == 1
        assert payload.model_dump(exclude_unset=True) == {"address": None, "active": False}
        assert category_ids is None

    async def test_coords_are_parsed_and_an_empty_value_clears_them(self, service, travel_times):
        await handle_location("add", {"name": "Home", "kind": "home", "coordinates": "41.1579, -8.6291"}, service, travel_times)
        assert service.create.call_args.args[0].coordinates == (41.1579, -8.6291)

        await handle_location("update", {"location": "1", "coordinates": ""}, service, travel_times)
        assert service.update.call_args.args[1].model_dump(exclude_unset=True) == {"coordinates": None}

    async def test_bad_coords_are_refused(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Home", "coordinates": "north"}, service, travel_times)
        assert exc.value.status_code in (400, 422)

    async def test_update_sells_replaces_categories(self, service, travel_times):
        await handle_location("update", {"location": "1", "sells": "groceries,bakery"}, service, travel_times)

        assert service.update.call_args.args[2] == [1, 2]

    async def test_delete(self, service, travel_times):
        result = await handle_location("delete", {"location": "Market"}, service, travel_times)

        service.delete.assert_awaited_once_with(1)
        assert result == {"id": 1, "name": "Market", "deleted": True}

    async def test_unknown_command(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("fly", {}, service, travel_times)
        assert exc.value.status_code == 400


class TestTravelFrom:
    async def test_add_saves_minutes_from_each_origin_to_the_new_location(self, service, travel_times):
        result = await handle_location("add", {"name": "Pharmacy", "travel_from": "home:foot=12,metro=8;office:car=10"}, service, travel_times)

        saved = [(c.args[0], c.args[1].destination_id, c.args[1].mode, c.args[1].minutes) for c in travel_times.set.await_args_list]
        assert saved == [(10, 1, "foot", 12), (10, 1, "metro", 8), (11, 1, "car", 10)]
        assert result["travel_times"] == []

    async def test_unknown_origin_is_refused_before_anything_is_created(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Pharmacy", "travel_from": "gym:foot=5"}, service, travel_times)

        assert exc.value.status_code == 400 and "gym" in exc.value.detail
        service.create.assert_not_awaited()

    async def test_an_explicit_origin_arrow_is_refused(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("update", {"location": "Market", "travel_from": "home>office:car=5"}, service, travel_times)

        assert exc.value.status_code == 400

    async def test_bad_syntax_is_400(self, service, travel_times):
        with pytest.raises(HTTPException) as exc:
            await handle_location("update", {"location": "Market", "travel_from": "home:car"}, service, travel_times)

        assert exc.value.status_code == 400

    async def test_update_saves_routes_after_the_fields(self, service, travel_times):
        await handle_location("update", {"location": "Market", "travel_from": "home:car=5"}, service, travel_times)

        service.update.assert_awaited_once()
        travel_times.set.assert_awaited_once()

    async def test_show_lists_travel_times(self, service, travel_times):
        travel_times.list_for.return_value = [SimpleNamespace(model_dump=lambda mode: {"id": 3, "mode": "car"})]

        result = await handle_location("show", {"location": "Market"}, service, travel_times)

        assert result["travel_times"] == [{"id": 3, "mode": "car"}]
        travel_times.list_for.assert_awaited_once_with(1)


class TestResolver:
    def test_add_with_flags(self):
        tokens = _parse_tokens(
            '/locationadd Pharmacy by school --kind pharmacy --hours "mon-fri 9-19; sat 9-13" --sells pharmacy'
        )
        resolved = _resolve_fragment(tokens[0], tokens[1:])

        assert resolved.type == "location" and resolved.command == "add"
        assert resolved.args["name"] == "Pharmacy by school"
        assert resolved.args["kind"] == "pharmacy"
        assert resolved.args["opening_hours"] == "mon-fri 9-19; sat 9-13"
        assert resolved.args["sells"] == "pharmacy"

    def test_from_flag(self):
        tokens = _parse_tokens('/locationupdate Pharmacy --from "home:foot=12;office:car=10"')
        resolved = _resolve_fragment(tokens[0], tokens[1:])

        assert resolved.args["travel_from"] == "home:foot=12;office:car=10"
