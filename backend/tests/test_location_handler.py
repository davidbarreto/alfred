from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.location import handle_location
from app.assistant.commands.resolver import _parse_tokens, _resolve_fragment
from app.features.organizer.locations.errors import LocationConflictError, LocationValidationError
from app.features.organizer.locations.schemas import LocationFilters, LocationRead

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _read(**kwargs):
    defaults = dict(
        id=1, name="Market", kind="supermarket", address=None, maps_url=None, opening_hours=None, notes=None,
        active=True, created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(kwargs)
    return LocationRead(**defaults)


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.create.return_value = _read()
    svc.update.return_value = _read()
    svc.find.return_value = _read()
    svc.list.return_value = [_read()]
    svc.category_ids_for.return_value = [1, 2]
    return svc


class TestAdd:
    async def test_builds_the_location_with_categories(self, service):
        result = await handle_location("add", {
            "name": "Market by school", "kind": "Supermarket", "opening_hours": "mon-fri 8-20", "sells": "groceries, bakery",
        }, service)

        payload = service.create.call_args.args[0]
        assert payload.name == "Market by school"
        assert payload.kind == "supermarket"
        assert payload.opening_hours == "mon-fri 8-20"
        assert payload.category_ids == [1, 2]
        service.category_ids_for.assert_awaited_once_with(["groceries", "bakery"])
        assert result["id"] == 1

    async def test_kind_defaults_to_other(self, service):
        await handle_location("add", {"name": "Post office"}, service)

        assert service.create.call_args.args[0].kind == "other"

    async def test_name_required(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": " "}, service)
        assert exc.value.status_code == 400

    async def test_conflict_is_409(self, service):
        service.create.side_effect = LocationConflictError("Home is already set")

        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Flat", "kind": "home"}, service)
        assert exc.value.status_code == 409

    async def test_bad_hours_are_422(self, service):
        service.create.side_effect = LocationValidationError("Opening hours: bad")

        with pytest.raises(HTTPException) as exc:
            await handle_location("add", {"name": "Market", "opening_hours": "x"}, service)
        assert exc.value.status_code == 422


class TestList:
    async def test_active_only_by_default(self, service):
        await handle_location("list", {}, service)

        assert service.list.call_args.args[0] == LocationFilters(active=True)

    async def test_all_kind_and_sells(self, service):
        service.category_ids_for.return_value = [4]

        await handle_location("list", {"all": "yes", "kind": "Pharmacy", "sells": "pharmacy"}, service)

        assert service.list.call_args.args[0] == LocationFilters(kind="pharmacy", active=None, category_id=4)


class TestShowUpdateDelete:
    async def test_show_by_name(self, service):
        result = await handle_location("show", {"location": "market"}, service)

        service.find.assert_awaited_once_with("market")
        assert result["name"] == "Market"

    async def test_unknown_location_is_404(self, service):
        service.find.return_value = None

        with pytest.raises(HTTPException) as exc:
            await handle_location("show", {"location": "nowhere"}, service)
        assert exc.value.status_code == 404

    async def test_update_clears_an_empty_field_and_archives(self, service):
        await handle_location("update", {"location": "Market", "address": "", "active": "false"}, service)

        location_id, payload = service.update.call_args.args
        assert location_id == 1
        assert payload.model_dump(exclude_unset=True) == {"address": None, "active": False}

    async def test_update_sells_replaces_categories(self, service):
        await handle_location("update", {"location": "1", "sells": "groceries,bakery"}, service)

        assert service.update.call_args.args[1].category_ids == [1, 2]

    async def test_delete(self, service):
        result = await handle_location("delete", {"location": "Market"}, service)

        service.delete.assert_awaited_once_with(1)
        assert result == {"id": 1, "name": "Market", "deleted": True}

    async def test_unknown_command(self, service):
        with pytest.raises(HTTPException) as exc:
            await handle_location("fly", {}, service)
        assert exc.value.status_code == 400


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
