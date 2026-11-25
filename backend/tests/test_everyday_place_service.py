from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.location.errors import LocationConflictError, LocationValidationError
from app.features.location.places.schemas import PlaceRead, PlaceUpdate
from app.features.organizer.everyday_places.schemas import EverydayPlaceCreate, EverydayPlaceFilters
from app.features.organizer.everyday_places.service import EverydayPlaceService

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_CITY = SimpleNamespace(id=15, name="Hometown", country=SimpleNamespace(id=1, name="Testland", code="TL"))


def _place(**kwargs):
    fields = dict(
        id=2, name="Market", kind="supermarket", city_id=15, city=_CITY, address=None, maps_url=None, latitude=None,
        longitude=None, opening_hours=None, notes=None, active=True, created_at=_NOW, updated_at=_NOW,
    )
    fields.update(kwargs)
    return SimpleNamespace(**fields)


_HOME = _place(id=1, name="Casa", kind="home")
_MARKET = _place()
_MUSEUM = _place(id=3, name="Museum", kind="museum")


@pytest.fixture
def places():
    rows = {p.id: p for p in (_HOME, _MARKET, _MUSEUM)}
    svc = AsyncMock()
    svc.get_row.side_effect = lambda place_id: rows.get(place_id)
    svc.reads.side_effect = lambda found: [PlaceRead.model_validate(p) for p in found]
    svc.add.return_value = _MARKET
    return svc


@pytest.fixture
def service(places):
    svc = EverydayPlaceService(session=AsyncMock(), places=places)
    svc._repo = AsyncMock()
    svc._repo.members.return_value = {2}
    svc._repo.categories_of.return_value = {2: [SimpleNamespace(id=1, name="groceries")]}
    svc._repo.get_categories.side_effect = lambda ids: [SimpleNamespace(id=i, name=f"c{i}") for i in ids if i < 5]
    svc._repo.add_member.return_value = True
    svc._repo.remove_member.return_value = True
    return svc


class TestReads:
    async def test_home_and_members_are_everyday_and_carry_categories(self, service):
        service._repo.list.return_value = [_HOME, _MARKET, _MUSEUM]

        rows = await service.list(EverydayPlaceFilters())

        assert [(r.name, r.everyday) for r in rows] == [("Casa", True), ("Market", True), ("Museum", False)]
        assert [c.name for c in rows[1].categories] == ["groceries"]

    async def test_get_any_place(self, service):
        assert (await service.get(3)).everyday is False
        assert await service.get(99) is None


class TestCreate:
    async def test_adds_the_place_the_membership_and_categories_then_commits_once(self, service, places):
        await service.create(EverydayPlaceCreate(name="Market", kind="supermarket", category_ids=[1, 1, 2]))

        sent = places.add.call_args.args[0]
        assert sent.name == "Market" and not hasattr(sent, "category_ids")
        service._repo.add_member.assert_awaited_once_with(2)
        service._repo.set_categories.assert_awaited_once_with(2, [1, 2])
        places.saved.assert_awaited_once_with(2, created=True)

    async def test_home_needs_no_membership_row(self, service, places):
        places.add.return_value = _HOME
        await service.create(EverydayPlaceCreate(name="Casa", kind="home"))
        service._repo.add_member.assert_not_awaited()

    async def test_unknown_category_is_refused_before_anything_is_written(self, service, places):
        with pytest.raises(LocationValidationError, match=r"\[7\]"):
            await service.create(EverydayPlaceCreate(name="Market", category_ids=[1, 7]))
        places.add.assert_not_awaited()


class TestUpdate:
    async def test_base_fields_go_to_the_place_service_and_categories_are_replaced(self, service, places):
        await service.update(2, PlaceUpdate(notes="Cash only"), category_ids=[3])

        places.update.assert_awaited_once_with(2, PlaceUpdate(notes="Cash only"))
        service._repo.set_categories.assert_awaited_once_with(2, [3])

    async def test_categories_alone_leave_the_place_untouched(self, service, places):
        await service.update(2, PlaceUpdate(), category_ids=[])
        places.update.assert_not_awaited()

    async def test_not_found(self, service, places):
        places.update.return_value = None
        assert await service.update(99, PlaceUpdate(notes="x")) is None
        assert await service.update(99, PlaceUpdate()) is None


class TestMembership:
    async def test_add_commits_a_new_member(self, service):
        assert (await service.add(3)).id == 3
        service._repo.add_member.assert_awaited_once_with(3)
        service._repo.commit.assert_awaited_once()

    async def test_add_home_or_an_existing_member_writes_nothing(self, service):
        await service.add(1)
        service._repo.add_member.return_value = False
        await service.add(2)
        service._repo.commit.assert_not_awaited()

    async def test_remove(self, service):
        assert await service.remove(2) is True
        service._repo.remove_member.assert_awaited_once_with(2)
        assert await service.remove(99) is False

    async def test_home_cannot_be_removed(self, service):
        with pytest.raises(LocationConflictError, match="always"):
            await service.remove(1)


class TestFind:
    async def test_an_everyday_name_wins(self, service, places):
        service._repo.list.return_value = [_HOME, _MARKET]
        assert (await service.find(" MARKET ")).id == 2
        places.find.assert_not_awaited()

    async def test_falls_back_to_any_place(self, service, places):
        service._repo.list.return_value = [_HOME]
        places.find.return_value = _MUSEUM
        assert (await service.find("museum")).id == 3
        places.find.return_value = None
        assert await service.find("nowhere") is None


class TestCategories:
    async def test_names_resolve_case_insensitively_in_order(self, service):
        service._repo.get_categories_by_name.return_value = [SimpleNamespace(id=2, name="Pharmacy"), SimpleNamespace(id=1, name="Groceries")]
        assert await service.category_ids_for(["groceries", " Pharmacy "]) == [1, 2]

    async def test_unknown_name(self, service):
        service._repo.get_categories_by_name.return_value = []
        with pytest.raises(LocationValidationError, match="Unknown shopping categories: bread"):
            await service.category_ids_for(["bread"])

    async def test_set_and_get(self, service):
        await service.set_categories(2, [1])
        service._repo.set_categories.assert_awaited_once_with(2, [1])
        service._repo.commit.assert_awaited_once()
        assert [c.name for c in await service.get_categories(2)] == ["groceries"]
        assert await service.get_categories(99) is None
