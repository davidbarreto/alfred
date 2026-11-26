from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.place import PlaceServices, handle_place
from app.assistant.commands.resolver import _parse_tokens, _resolve_fragment
from app.features.location.errors import LocationConflictError, LocationValidationError
from app.features.organizer.everyday_places.constants import default_everyday
from app.features.organizer.everyday_places.schemas import EverydayPlaceFilters
from app.features.travel.places.detail import TravelPlaceDetail
from app.features.travel.places.schemas import TravelPlaceRead
from place_read_helpers import CITY, everyday_read, place_fields

_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_LISBON = SimpleNamespace(id=2, name="Lisbon", country=SimpleNamespace(name="Portugal"))


def _read(**kwargs):
    return everyday_read(**{"opening_hours": None, "today": None, "categories": [], **kwargs})


def _travel(**kwargs):
    return TravelPlaceRead(**place_fields(**{"today": None, **kwargs}), tags=["would return"], grade=4.5, grade_count=2)


@pytest.fixture
def services():
    s = PlaceServices(
        places=AsyncMock(), everyday=AsyncMock(), travel_times=AsyncMock(), travel=AsyncMock(), visits=AsyncMock(),
        costs=AsyncMock(), cities=AsyncMock(),
    )
    s.everyday.create.return_value = _read()
    s.everyday.update.return_value = _read()
    s.everyday.find.return_value = _read()
    s.everyday.get.return_value = _read()
    s.everyday.list.return_value = [_read()]
    s.everyday.category_ids_for.return_value = [1, 2]
    s.places.create.return_value = _read(id=5, kind="restaurant")
    s.travel.get_place_detail.return_value = None
    s.travel.get_places.return_value = [_travel()]
    s.costs.get_place_costs.return_value = None
    s.cities.get_cities.return_value = []
    s.travel_times.list_for.return_value = []
    s.travel_times.find_place.side_effect = (
        lambda name: SimpleNamespace(id={"home": 10, "office": 11}[name]) if name in ("home", "office") else None
    )
    return s


async def run(command, arguments, services):
    return await handle_place(command, arguments, services)


class TestEverydayDefaults:
    @pytest.mark.parametrize("kind,expected", [
        ("supermarket", True), ("home", True), ("work", True), ("hotel", False), ("museum", False),
        ("restaurant", None), ("cafe", None), ("other", None),
    ])
    def test_kind_decides_or_asks(self, kind, expected):
        assert default_everyday(kind) is expected


class TestAdd:
    async def test_an_everyday_kind_becomes_an_everyday_place_with_what_it_sells(self, services):
        result = await run("add", {
            "name": "Market by school", "kind": "Supermarket", "opening_hours": "mon-fri 8-20", "sells": "groceries, bakery",
        }, services)

        payload = services.everyday.create.call_args.args[0]
        assert (payload.name, payload.kind, payload.opening_hours) == ("Market by school", "supermarket", "mon-fri 8-20")
        assert payload.category_ids == [1, 2] and payload.city_id is None
        services.everyday.category_ids_for.assert_awaited_once_with(["groceries", "bakery"])
        services.places.create.assert_not_awaited()
        assert result["id"] == 1 and result["country"] == "Testland"

    async def test_a_trip_kind_is_a_plain_place_with_its_tags(self, services):
        services.cities.get_cities.return_value = [_LISBON]

        await run("add", {"name": "Hotel Example", "kind": "hotel", "city": "lisbon", "tags": "Would return"}, services)

        payload = services.places.create.call_args.args[0]
        assert (payload.kind, payload.city_id) == ("hotel", 2)
        services.everyday.create.assert_not_awaited()
        assert services.travel.update_place.await_args.args[0] == 5
        assert services.travel.update_place.await_args.args[1].tags == ["would return"]

    async def test_a_kind_that_could_be_either_asks(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Cafe Example", "kind": "cafe"}, services)

        assert exc.value.status_code == 400 and "--everyday" in exc.value.detail
        services.places.create.assert_not_awaited()
        services.everyday.create.assert_not_awaited()

    async def test_everyday_false_on_a_restaurant(self, services):
        await run("add", {"name": "Bistro Example", "kind": "restaurant", "everyday": "false"}, services)

        services.places.create.assert_awaited_once()
        services.everyday.create.assert_not_awaited()

    async def test_everyday_true_overrides_the_kind(self, services):
        await run("add", {"name": "Hotel bar", "kind": "hotel", "everyday": "yes"}, services)

        services.everyday.create.assert_awaited_once()

    async def test_home_is_never_a_non_everyday_place(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Flat", "kind": "home", "everyday": "false"}, services)
        assert exc.value.status_code == 400

    async def test_sells_on_a_non_everyday_place_is_refused_before_writing(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Hotel Example", "kind": "hotel", "sells": "groceries"}, services)
        assert exc.value.status_code == 400 and "everyday" in exc.value.detail
        services.places.create.assert_not_awaited()

    async def test_a_new_city_needs_its_country(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Hotel Example", "kind": "hotel", "city": "Atlantis"}, services)
        assert exc.value.status_code == 400 and "--country" in exc.value.detail
        services.cities.create_city.assert_not_awaited()

    async def test_a_new_city_with_its_country_is_created(self, services):
        services.cities.create_city.return_value = SimpleNamespace(id=9)

        await run("add", {"name": "Hotel Example", "kind": "hotel", "city": "Atlantis", "country": "Examplia"}, services)

        created = services.cities.create_city.await_args.args[0]
        assert (created.name, created.country) == ("Atlantis", "Examplia")
        assert services.places.create.call_args.args[0].city_id == 9

    async def test_a_city_in_two_countries_is_refused(self, services):
        services.cities.get_cities.return_value = [
            _LISBON, SimpleNamespace(id=3, name="Lisbon", country=SimpleNamespace(name="Examplia")),
        ]
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Hotel Example", "kind": "hotel", "city": "Lisbon"}, services)
        assert exc.value.status_code == 400 and "Examplia" in exc.value.detail

    async def test_unknown_kind_is_400_listing_the_kinds(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Head office", "kind": "office", "everyday": "true"}, services)
        assert exc.value.status_code == 400 and "'work'" in exc.value.detail

    async def test_name_required(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": " "}, services)
        assert exc.value.status_code == 400

    async def test_conflict_is_409(self, services):
        services.everyday.create.side_effect = LocationConflictError("Home is already set")
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Flat", "kind": "home"}, services)
        assert exc.value.status_code == 409

    async def test_bad_hours_are_422(self, services):
        services.everyday.create.side_effect = LocationValidationError("Opening hours: bad")
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Market", "kind": "market", "opening_hours": "x"}, services)
        assert exc.value.status_code == 422

    async def test_coords_are_parsed(self, services):
        await run("add", {"name": "Home", "kind": "home", "coordinates": "41.1579, -8.6291"}, services)
        assert services.everyday.create.call_args.args[0].coordinates == (41.1579, -8.6291)

    async def test_bad_coords_are_refused(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Home", "kind": "home", "coordinates": "north"}, services)
        assert exc.value.status_code in (400, 422)


class TestList:
    async def test_everyday_view_active_only_by_default(self, services):
        result = await run("list", {}, services)

        assert services.everyday.list.call_args.args[0] == EverydayPlaceFilters(active=True)
        assert result["view"] == "everyday" and result["places"][0]["name"] == "Market"

    async def test_everyday_view_with_all_kind_and_sells(self, services):
        services.everyday.category_ids_for.return_value = [4]

        await run("list", {"all": "yes", "kind": "Pharmacy", "sells": "pharmacy", "q": "school"}, services)

        assert services.everyday.list.call_args.args[0] == EverydayPlaceFilters(
            kind="pharmacy", active=None, category_id=4, q="school"
        )

    async def test_visited_view_lists_places_with_history_and_grades(self, services):
        result = await run("list", {
            "view": "visited", "kind": "hotel", "city": "Lisbon", "tag": "A,B", "min_grade": "4", "ungraded": "no",
        }, services)

        f = services.travel.get_places.await_args.args[0]
        assert (f.status, f.kind, f.city, f.tag, f.min_grade, f.ungraded, f.active) == (
            "visited", "hotel", "Lisbon", ["A", "B"], 4, False, True
        )
        assert result["places"][0]["grade"] == 4.5 and result["places"][0]["tags"] == ["would return"]

    async def test_all_view_includes_places_never_visited(self, services):
        await run("list", {"view": "all", "all": "true"}, services)

        f = services.travel.get_places.await_args.args[0]
        assert f.status is None and f.active is None

    async def test_planned_view_asks_for_planned_places(self, services):
        await run("list", {"view": "planned"}, services)

        assert services.travel.get_places.await_args.args[0].status == "planned"

    async def test_travel_filters_on_the_everyday_view_are_refused(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("list", {"city": "Lisbon"}, services)
        assert exc.value.status_code == 400 and "--view" in exc.value.detail

    async def test_sells_on_the_visited_view_is_refused(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("list", {"view": "visited", "sells": "groceries"}, services)
        assert exc.value.status_code == 400

    async def test_unknown_view(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("list", {"view": "favourites"}, services)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("view", ["everyday", "visited"])
    async def test_unknown_kind_filter_is_422(self, services, view):
        services.everyday.list.side_effect = None
        with pytest.raises(HTTPException) as exc:
            await run("list", {"kind": "office", "view": view}, services)
        assert exc.value.status_code == 422 and "work" in exc.value.detail
        services.travel.get_places.assert_not_awaited()


class TestShow:
    async def test_by_name_composes_the_three_views(self, services):
        services.travel.get_place_detail.return_value = TravelPlaceDetail(**dict(_travel()), visits=[], stays=[])
        services.costs.get_place_costs.return_value = SimpleNamespace(
            total=SimpleNamespace(model_dump=lambda mode: {"total_eur": "80.00"})
        )
        services.travel_times.list_for.return_value = [SimpleNamespace(model_dump=lambda mode: {"id": 3, "mode": "car"})]

        result = await run("show", {"place": "market"}, services)

        services.everyday.find.assert_awaited_once_with("market")
        assert result["everyday"] is True and result["sells"] == [] and "categories" not in result
        assert result["grade"] == 4.5 and result["tags"] == ["would return"] and result["visits"] == []
        assert result["travel_times"] == [{"id": 3, "mode": "car"}]
        assert result["lifetime_cost"] == {"total_eur": "80.00"}

    async def test_with_a_city_looks_only_there(self, services):
        services.cities.get_cities.return_value = [_LISBON]
        services.places.find.return_value = SimpleNamespace(id=7)
        services.everyday.get.return_value = _read(id=7, name="Cafe Example", kind="cafe", everyday=False)

        result = await run("show", {"place": "Cafe Example", "city": "Lisbon"}, services)

        services.places.find.assert_awaited_once_with("Cafe Example", 2)
        services.everyday.find.assert_not_awaited()
        assert result["id"] == 7 and result["everyday"] is False

    async def test_an_unknown_city_is_404(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("show", {"place": "Cafe Example", "city": "Atlantis", "country": "Examplia"}, services)
        assert exc.value.status_code == 404
        services.cities.create_city.assert_not_awaited()

    async def test_unknown_place_is_404(self, services):
        services.everyday.find.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run("show", {"place": "nowhere"}, services)
        assert exc.value.status_code == 404

    async def test_a_name_in_several_cities_is_409(self, services):
        services.everyday.find.side_effect = LocationConflictError("Several places are called 'Cafe'")
        with pytest.raises(HTTPException) as exc:
            await run("show", {"place": "Cafe"}, services)
        assert exc.value.status_code == 409


class TestUpdate:
    async def test_clears_an_empty_field_and_archives(self, services):
        await run("update", {"place": "Market", "address": "", "active": "false"}, services)

        place_id, payload, category_ids = services.everyday.update.call_args.args
        assert place_id == 1
        assert payload.model_dump(exclude_unset=True) == {"address": None, "active": False}
        assert category_ids is None

    async def test_empty_coords_clear_them(self, services):
        await run("update", {"place": "1", "coordinates": ""}, services)
        assert services.everyday.update.call_args.args[1].model_dump(exclude_unset=True) == {"coordinates": None}

    async def test_sells_replaces_categories(self, services):
        await run("update", {"place": "1", "sells": "groceries,bakery"}, services)
        assert services.everyday.update.call_args.args[2] == [1, 2]

    async def test_city_moves_the_place_and_does_not_narrow_the_lookup(self, services):
        services.cities.get_cities.return_value = [_LISBON]

        await run("update", {"place": "Market", "city": "Lisbon"}, services)

        services.everyday.find.assert_awaited_once_with("Market")
        assert services.everyday.update.call_args.args[1].city_id == 2

    async def test_tags_replace_the_travel_tags(self, services):
        await run("update", {"place": "Market", "tags": ""}, services)

        services.travel.update_place.assert_awaited_once()
        assert services.travel.update_place.await_args.args[1].tags == []
        services.everyday.update.assert_not_awaited()

    async def test_everyday_on_and_off(self, services):
        services.everyday.find.return_value = _read(everyday=False, kind="cafe")
        await run("update", {"place": "Cafe", "everyday": "true"}, services)
        services.everyday.add.assert_awaited_once_with(1)

        await run("update", {"place": "Cafe", "everyday": "false"}, services)
        services.everyday.remove.assert_awaited_once_with(1)

    async def test_sells_on_a_place_that_is_not_everyday_is_refused(self, services):
        services.everyday.find.return_value = _read(everyday=False, kind="cafe")
        with pytest.raises(HTTPException) as exc:
            await run("update", {"place": "Cafe", "sells": "groceries"}, services)
        assert exc.value.status_code == 400
        services.everyday.update.assert_not_awaited()


class TestTravelFrom:
    async def test_add_saves_minutes_from_each_origin_to_the_new_place(self, services):
        await run("add", {"name": "Pharmacy", "kind": "pharmacy", "travel_from": "home:foot=12,metro=8;office:car=10"}, services)

        saved = [(c.args[0], c.args[1].destination_id, c.args[1].mode, c.args[1].minutes)
                 for c in services.travel_times.set.await_args_list]
        assert saved == [(10, 1, "foot", 12), (10, 1, "metro", 8), (11, 1, "car", 10)]

    async def test_unknown_origin_is_refused_before_anything_is_created(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("add", {"name": "Pharmacy", "kind": "pharmacy", "travel_from": "gym:foot=5"}, services)
        assert exc.value.status_code == 400 and "gym" in exc.value.detail
        services.everyday.create.assert_not_awaited()

    async def test_an_explicit_origin_arrow_is_refused(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("update", {"place": "Market", "travel_from": "home>office:car=5"}, services)
        assert exc.value.status_code == 400

    async def test_bad_syntax_is_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("update", {"place": "Market", "travel_from": "home:car"}, services)
        assert exc.value.status_code == 400

    async def test_update_saves_only_the_routes(self, services):
        await run("update", {"place": "Market", "travel_from": "home:car=5"}, services)

        services.everyday.update.assert_not_awaited()
        services.travel_times.set.assert_awaited_once()


class TestGrade:
    async def test_grade_after_the_name_logs_a_visited_visit_without_a_trip(self, services):
        services.visits.create_visit.return_value = SimpleNamespace(id=21, grade=4, visit_date=date(2026, 11, 25))
        services.travel.get_place.return_value = _travel()

        with patch("app.assistant.commands.handlers.place.local_today", return_value=date(2026, 11, 25)):
            result = await run("grade", {"place": "Cafe Example 4"}, services)

        services.everyday.find.assert_awaited_once_with("Cafe Example")
        visit = services.visits.create_visit.await_args.args[0]
        assert (visit.place_id, visit.status, visit.grade, visit.trip_id, visit.visit_date) == (
            1, "visited", 4, None, date(2026, 11, 25)
        )
        assert result["id"] == 21 and "4/5" in result["message"] and "4.5" in result["message"]

    async def test_grade_as_a_field_with_date_and_notes(self, services):
        services.visits.create_visit.return_value = SimpleNamespace(id=21, grade=5, visit_date=date(2026, 11, 20))
        services.travel.get_place.return_value = None

        await run("grade", {"place": "Cafe Example", "grade": 5, "date": "2026-11-20", "notes": "Great coffee"}, services)

        visit = services.visits.create_visit.await_args.args[0]
        assert (visit.grade, visit.visit_date, visit.notes) == (5, date(2026, 11, 20), "Great coffee")

    async def test_without_a_grade_is_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("grade", {"place": "Cafe Example"}, services)
        assert exc.value.status_code == 400
        services.visits.create_visit.assert_not_awaited()

    async def test_out_of_range_grade_is_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("grade", {"place": "Cafe Example", "grade": "7"}, services)
        assert exc.value.status_code == 400


class TestArchiveDelete:
    async def test_archive_and_unarchive(self, services):
        await run("archive", {"place": "Market"}, services)
        assert services.places.update.await_args.args[1].active is False

        result = await run("unarchive", {"place": "Market"}, services)
        assert services.places.update.await_args.args[1].active is True and result["active"] is True

    async def test_delete(self, services):
        services.places.delete.return_value = True
        result = await run("delete", {"place": "Market"}, services)
        services.places.delete.assert_awaited_once_with(1)
        assert result == {"id": 1, "name": "Market", "deleted": True}

    async def test_delete_in_use_is_409(self, services):
        services.places.delete.side_effect = LocationConflictError("'Market' can't be deleted: it has 1 visit(s)")
        with pytest.raises(HTTPException) as exc:
            await run("delete", {"place": "Market"}, services)
        assert exc.value.status_code == 409

    async def test_unknown_command(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("fly", {}, services)
        assert exc.value.status_code == 400


class TestResolver:
    def test_add_with_flags(self):
        tokens = _parse_tokens(
            '/placeadd Pharmacy by school --kind pharmacy --hours "mon-fri 9-19; sat 9-13" --sells pharmacy --everyday true'
        )
        resolved = _resolve_fragment(tokens[0], tokens[1:])

        assert resolved.type == "place" and resolved.command == "add"
        assert resolved.args["name"] == "Pharmacy by school"
        assert resolved.args["kind"] == "pharmacy" and resolved.args["everyday"] == "true"
        assert resolved.args["opening_hours"] == "mon-fri 9-19; sat 9-13"
        assert resolved.args["sells"] == "pharmacy"

    def test_from_flag(self):
        tokens = _parse_tokens('/placeupdate Pharmacy --from "home:foot=12;office:car=10"')
        resolved = _resolve_fragment(tokens[0], tokens[1:])
        assert resolved.args["travel_from"] == "home:foot=12;office:car=10"

    def test_grade_keeps_the_whole_name_with_the_grade(self):
        resolved = _resolve_fragment("/placegrade", ["Cafe", "Example", "4"])
        assert (resolved.type, resolved.command, resolved.args["place"]) == ("place", "grade", "Cafe Example 4")

    def test_list_view(self):
        resolved = _resolve_fragment("/places", ["--view", "visited", "--min-grade", "4"])
        assert resolved.args == {"view": "visited", "min_grade": "4"}
