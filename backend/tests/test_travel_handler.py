from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.travel import TravelServices, handle_travel
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.legs.schemas import LegCreate, LegRead, LegUpdate
from app.features.travel.places.schemas import PlaceCreate, PlaceRead
from app.features.travel.places.service import PlaceInUseError
from app.features.travel.stays.schemas import StayCreate, StayRead
from app.features.travel.transaction_links.schemas import Cost, LinkedTransactions, TripCosts
from app.features.travel.transaction_links.service import TransferNotLinkableError
from app.features.travel.trips.schemas import TripCreate, TripDetail, TripRead
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trip(id=1, name="Example trip", **kw):
    return TripRead(
        id=id, name=name, start_date=date(2031, 12, 17), end_date=date(2031, 12, 24), travelers=None, preferences=None,
        checklist_note_id=None, notes=None, default_tag_names=None, tags=["Family"], created_at=NOW, updated_at=NOW, **kw,
    )


def _place(id=3, name="Hotel Example", kind="hotel", **kw):
    base = dict(id=id, kind=kind, name=name, city="Lisbon", country=None, maps_url=None, lat=None, lng=None, address=None,
                notes=None, tags=[], grade=None, grade_count=0, created_at=NOW, updated_at=NOW)
    base.update(kw)
    return PlaceRead(**base)


def _leg(id=1):
    return LegRead(
        id=id, trip_id=1, mode="flight", origin="Alpha", destination="Beta", origin_code=None, destination_code=None,
        departs_at=datetime(2031, 12, 17, 6, tzinfo=timezone.utc), arrives_at=datetime(2031, 12, 17, 9, tzinfo=timezone.utc),
        departs_tz="UTC", arrives_tz="Europe/Stockholm", carrier="XX", number="12", booking_ref=None, booking_url=None,
        seat=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _stay(id=7):
    return StayRead(
        id=id, trip_id=1, place_id=3, place=_place(), check_in_at=datetime(2031, 12, 18, 14, tzinfo=timezone.utc),
        check_out_at=datetime(2031, 12, 20, 10, tzinfo=timezone.utc), timezone="UTC", booking_ref=None, booking_url=None,
        notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _visit(id=11, status="planned", grade=None):
    return VisitRead(
        id=id, place_id=3, place=VisitPlace(id=3, kind="museum", name="Museum Example", city="Lisbon", maps_url=None, lat=None, lng=None),
        trip_id=1, trip_name="Example trip", status=status, visit_date=date(2031, 12, 18), visit_time=time(10, 0), notes=None,
        grade=grade, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def services():
    s = TravelServices(
        trips=AsyncMock(), legs=AsyncMock(), stays=AsyncMock(), places=AsyncMock(), visits=AsyncMock(),
        links=AsyncMock(), default_tags=AsyncMock(), recap=AsyncMock(),
    )
    return s


async def run(cmd_type, command, arguments, services):
    return await handle_travel(cmd_type, command, arguments, services)


class TestTrips:
    async def test_list_defaults_to_current_and_summarises(self, services):
        services.trips.get_trips.return_value = [_trip()]
        result = await run("travel_trip", "list", {}, services)
        assert services.trips.get_trips.await_args.args[0].status == "current"
        assert result["trips"][0] == {
            "id": 1, "name": "Example trip", "start_date": "2031-12-17", "end_date": "2031-12-24",
            "status": "upcoming", "travelers": None, "tags": ["Family"],
        }

    async def test_list_passes_filters(self, services):
        services.trips.get_trips.return_value = []
        await run("travel_trip", "list", {"status": "past", "tag": "Family, Work", "q": "ex", "limit": "5"}, services)
        f = services.trips.get_trips.await_args.args[0]
        assert (f.status, f.tag, f.q, f.limit) == ("past", ["Family", "Work"], "ex", 5)

    async def test_list_rejects_an_unknown_status(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "list", {"status": "sometime"}, services)
        assert exc.value.status_code == 400 and "status must be one of" in exc.value.detail

    async def test_add_builds_the_trip(self, services):
        services.trips.create_trip.return_value = _trip()
        result = await run("travel_trip", "add", {
            "name": "Example trip", "start": "2031-12-17", "end": "2031-12-24", "tags": "Family, Work", "finance_tags": "Travel, Hotel",
        }, services)
        data: TripCreate = services.trips.create_trip.await_args.args[0]
        assert (data.start_date, data.end_date, data.tags, data.default_tag_names) == (
            date(2031, 12, 17), date(2031, 12, 24), ["Family", "Work"], "Travel, Hotel",
        )
        assert result["id"] == 1

    async def test_add_with_a_bad_date_is_a_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "add", {"name": "X", "start": "17/12/2031", "end": "2031-12-24"}, services)
        assert exc.value.status_code == 400 and "start must be a date" in exc.value.detail

    async def test_add_without_dates_is_a_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "add", {"name": "X"}, services)
        assert exc.value.status_code == 400

    async def test_update_only_sends_what_was_given_and_empty_clears(self, services):
        services.trips.update_trip.return_value = _trip()
        await run("travel_trip", "update", {"id": "1", "notes": "", "tags": "A"}, services)
        update = services.trips.update_trip.await_args.args[1]
        assert update.model_dump(exclude_unset=True) == {"notes": None, "tags": ["A"]}

    async def test_update_nothing_is_a_400(self, services):
        with pytest.raises(HTTPException):
            await run("travel_trip", "update", {"id": "1"}, services)

    async def test_update_unknown_trip_is_a_404(self, services):
        services.trips.update_trip.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "update", {"id": "9", "name": "x"}, services)
        assert exc.value.status_code == 404

    async def test_service_value_errors_become_400(self, services):
        services.trips.update_trip.side_effect = ValueError("end_date cannot be before start_date")
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "update", {"id": "1", "end": "2031-01-01"}, services)
        assert exc.value.status_code == 400 and "end_date" in exc.value.detail

    async def test_get_by_id_summarises_everything(self, services):
        services.trips.get_trip.return_value = _trip()
        services.trips.get_trip_detail.return_value = TripDetail(
            **_trip().model_dump(exclude={"status"}), legs=[_leg()], stays=[_stay()], timeline=[], warnings=[],
            visits=[_visit()], hidden_visit_count=2, leave_home_at=datetime(2031, 12, 17, 3, tzinfo=timezone.utc),
        )
        services.links.get_trip_costs.return_value = TripCosts(
            total=Cost(total_eur="25.50", transaction_count=2), by_kind=[], legs=[], stays=[], visits=[]
        )
        result = await run("travel_trip", "get", {"trip": "1"}, services)
        assert result["legs"][0]["departs"] == "2031-12-17T06:00" and result["legs"][0]["arrives"] == "2031-12-17T10:00"
        assert result["stays"][0]["place"] == "Hotel Example" and result["visits"][0]["time"] == "10:00"
        assert result["hidden_visits"] == 2 and result["leave_home_at"].startswith("2031-12-17T03:00")
        assert result["cost"]["total_eur"] == "25.50"
        assert services.trips.get_trip_detail.await_args.kwargs == {"include_all_visits": False}

    async def test_get_by_name_prefers_current_trips_then_past(self, services):
        services.trips.get_trips.side_effect = [[], [_trip(name="Old trip")]]
        services.trips.get_trip_detail.return_value = TripDetail(
            **_trip(name="Old trip").model_dump(exclude={"status"}), legs=[], stays=[], timeline=[], warnings=[]
        )
        services.links.get_trip_costs.return_value = None
        result = await run("travel_trip", "get", {"trip": "old"}, services)
        assert result["name"] == "Old trip"
        scopes = [c.args[0].status for c in services.trips.get_trips.await_args_list]
        assert scopes == ["current", "past"]

    async def test_get_next_means_the_soonest_current_trip(self, services):
        services.trips.get_trips.return_value = [_trip()]
        services.trips.get_trip_detail.return_value = TripDetail(
            **_trip().model_dump(exclude={"status"}), legs=[], stays=[], timeline=[], warnings=[]
        )
        services.links.get_trip_costs.return_value = None
        result = await run("travel_trip", "get", {"trip": "next"}, services)
        f = services.trips.get_trips.await_args.args[0]
        assert (f.status, f.q, f.limit) == ("current", None, 1) and result["cost"] is None

    async def test_get_unknown_name_is_a_404(self, services):
        services.trips.get_trips.return_value = []
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "get", {"trip": "atlantis"}, services)
        assert exc.value.status_code == 404

    async def test_delete_costs_and_apply_tags(self, services):
        services.trips.delete_trip.return_value = True
        assert "deleted" in (await run("travel_trip", "delete", {"id": "1"}, services))["message"]
        services.links.get_trip_costs.return_value = None
        with pytest.raises(HTTPException):
            await run("travel_trip", "costs", {"id": "1"}, services)
        services.default_tags.apply_to_existing.return_value = (["Travel"], 3)
        assert (await run("travel_trip", "apply_tags", {"id": "1"}, services))["added"] == 3
        services.default_tags.apply_to_existing.return_value = ([], 0)
        assert (await run("travel_trip", "apply_tags", {"id": "1"}, services))["tags"] == []


class TestRecapAndFilters:
    async def test_recap_by_name_returns_the_recap(self, services):
        from app.features.travel.recap.schemas import TripRecap

        services.trips.get_trips.return_value = [_trip()]
        services.recap.get_recap.return_value = TripRecap(
            trip_id=1, name="Example trip", start_date=date(2031, 12, 17), end_date=date(2031, 12, 24), status="past", days=8,
            leg_count=2, stay_count=1, visits_visited=3, visits_missed=1, visits_planned=0, cities=["Lisbon"], countries=[],
            spend=Cost(total_eur="250.00", transaction_count=3), spend_by_kind=[], to_complete=[], highlights=[],
        )
        result = await run("travel_trip", "recap", {"trip": "example"}, services)
        assert result["days"] == 8 and result["spend"]["total_eur"] == "250.00"
        services.recap.get_recap.assert_awaited_once_with(1)

    async def test_recap_needs_a_trip(self, services):
        with pytest.raises(HTTPException):
            await run("travel_trip", "recap", {}, services)

    async def test_trip_list_filters_by_city_and_country(self, services):
        services.trips.get_trips.return_value = []
        await run("travel_trip", "list", {"city": "Lisbon", "country": "Portugal"}, services)
        f = services.trips.get_trips.await_args.args[0]
        assert (f.city, f.country) == ("Lisbon", "Portugal")

    async def test_place_list_can_ask_for_ungraded_places(self, services):
        services.places.get_places.return_value = []
        await run("travel_place", "list", {"ungraded": "true"}, services)
        assert services.places.get_places.await_args.args[0].ungraded is True


class TestLegs:
    ARGS = {
        "trip_id": "1", "mode": "flight", "origin": "Alpha", "destination": "Beta", "departs": "2031-12-17T06:30",
        "arrives": "2031-12-17T10:00", "departs_tz": "UTC", "arrives_tz": "Europe/Stockholm", "carrier": "XX", "number": "12",
    }

    async def test_add(self, services):
        services.legs.create_leg.return_value = _leg()
        await run("travel_leg", "add", self.ARGS, services)
        data: LegCreate = services.legs.create_leg.await_args.args[0]
        assert data.trip_id == 1 and data.arrives_at == datetime(2031, 12, 17, 9, tzinfo=timezone.utc)

    async def test_add_without_zones_is_a_400_naming_them(self, services):
        args = {k: v for k, v in self.ARGS.items() if k not in ("departs_tz", "arrives_tz")}
        with pytest.raises(HTTPException) as exc:
            await run("travel_leg", "add", args, services)
        assert exc.value.status_code == 400 and "departs_tz" in exc.value.detail

    async def test_add_conflict_is_a_409(self, services):
        services.legs.create_leg.side_effect = TravelConflictError("already imported")
        with pytest.raises(HTTPException) as exc:
            await run("travel_leg", "add", self.ARGS, services)
        assert exc.value.status_code == 409

    async def test_update_maps_times_and_clears_empties(self, services):
        services.legs.update_leg.return_value = _leg()
        await run("travel_leg", "update", {"id": "1", "arrives": "2031-12-17T11:00", "seat": ""}, services)
        update: LegUpdate = services.legs.update_leg.await_args.args[1]
        assert update.model_dump(exclude_unset=True) == {"arrives_at": datetime(2031, 12, 17, 11), "seat": None}

    async def test_delete_unknown(self, services):
        services.legs.delete_leg.return_value = False
        with pytest.raises(HTTPException) as exc:
            await run("travel_leg", "delete", {"id": "1"}, services)
        assert exc.value.status_code == 404


class TestStays:
    async def test_add_with_a_new_hotel_creates_the_place_first(self, services):
        services.places.get_places.return_value = []
        services.places.create_place.return_value = _place()
        services.stays.create_stay.return_value = _stay()
        await run("travel_stay", "add", {
            "trip_id": "1", "hotel": "Hotel Example", "city": "Lisbon", "check_in": "2031-12-18T15:00",
            "check_out": "2031-12-20T11:00", "tz": "Europe/Lisbon",
        }, services)
        place: PlaceCreate = services.places.create_place.await_args.args[0]
        assert (place.kind, place.name, place.city) == ("hotel", "Hotel Example", "Lisbon")
        data: StayCreate = services.stays.create_stay.await_args.args[0]
        assert data.place_id == 3 and data.trip_id == 1

    async def test_add_reuses_a_hotel_with_the_same_name(self, services):
        services.places.get_places.return_value = [_place(), _place(id=4, name="Hotel Example Annex")]
        services.stays.create_stay.return_value = _stay()
        await run("travel_stay", "add", {
            "trip_id": "1", "hotel": "hotel example", "city": "Lisbon", "check_in": "2031-12-18T15:00",
            "check_out": "2031-12-20T11:00", "tz": "UTC",
        }, services)
        services.places.create_place.assert_not_awaited()
        assert services.stays.create_stay.await_args.args[0].place_id == 3

    async def test_add_with_a_place_id_never_creates(self, services):
        services.places.get_place.return_value = _place()
        services.stays.create_stay.return_value = _stay()
        await run("travel_stay", "add", {
            "trip_id": "1", "place": "3", "check_in": "2031-12-18T15:00", "check_out": "2031-12-20T11:00", "tz": "UTC",
        }, services)
        services.places.create_place.assert_not_awaited()

    async def test_unknown_place_id_is_a_404(self, services):
        services.places.get_place.return_value = None
        with pytest.raises(HTTPException) as exc:
            await run("travel_stay", "add", {"trip_id": "1", "place": "9", "check_in": "2031-12-18T15:00",
                                              "check_out": "2031-12-20T11:00", "tz": "UTC"}, services)
        assert exc.value.status_code == 404

    async def test_update_grade(self, services):
        services.stays.update_stay.return_value = _stay()
        await run("travel_stay", "update", {"id": "7", "grade": "4"}, services)
        assert services.stays.update_stay.await_args.args[1].grade == 4

    async def test_bad_grade_is_a_400(self, services):
        with pytest.raises(HTTPException):
            await run("travel_stay", "update", {"id": "7", "grade": "great"}, services)


class TestPlaces:
    async def test_add_defaults_the_kind(self, services):
        services.places.create_place.return_value = _place()
        await run("travel_place", "add", {"name": "Cafe Example", "city": "Lisbon", "tags": "Would return"}, services)
        data: PlaceCreate = services.places.create_place.await_args.args[0]
        assert (data.kind, data.tags) == ("other", ["Would return"])

    async def test_add_with_a_bad_kind_is_a_400(self, services):
        with pytest.raises(HTTPException) as exc:
            await run("travel_place", "add", {"name": "X", "kind": "spaceship"}, services)
        assert exc.value.status_code == 400

    async def test_list_passes_filters(self, services):
        services.places.get_places.return_value = [_place(grade=4.5, grade_count=2)]
        result = await run("travel_place", "list", {"q": "ex", "kind": "hotel", "min_grade": "4", "no_trip": "true", "tag": "A,B"}, services)
        f = services.places.get_places.await_args.args[0]
        assert (f.q, f.kind, f.min_grade, f.no_trip, f.tag) == ("ex", "hotel", 4, True, ["A", "B"])
        assert result["places"][0]["grade"] == 4.5

    async def test_get_returns_history_and_lifetime_cost(self, services):
        services.places.get_place.return_value = _place()
        services.places.get_place_detail.return_value = SimpleNamespace(
            **_place().model_dump(), visits=[_visit()], stays=[_stay()],
        )
        services.links.get_place_costs.return_value = SimpleNamespace(total=Cost(total_eur="80.00", transaction_count=2))
        result = await run("travel_place", "get", {"place": "3"}, services)
        assert len(result["visits"]) == 1 and len(result["stays"]) == 1 and result["lifetime_cost"]["total_eur"] == "80.00"

    async def test_get_by_name_needs_an_exact_match(self, services):
        services.places.get_places.return_value = [_place(name="Hotel Example Annex")]
        with pytest.raises(HTTPException) as exc:
            await run("travel_place", "get", {"place": "Hotel Example"}, services)
        assert exc.value.status_code == 404

    async def test_update_coordinates(self, services):
        services.places.update_place.return_value = _place()
        await run("travel_place", "update", {"id": "3", "lat": "38,7", "lng": "-9.1"}, services)
        update = services.places.update_place.await_args.args[1]
        assert (update.lat, update.lng) == (38.7, -9.1)

    async def test_bad_coordinate_is_a_400(self, services):
        with pytest.raises(HTTPException):
            await run("travel_place", "update", {"id": "3", "lat": "north"}, services)

    async def test_delete_in_use_is_a_409(self, services):
        services.places.delete_place.side_effect = PlaceInUseError(3)
        with pytest.raises(HTTPException) as exc:
            await run("travel_place", "delete", {"id": "3"}, services)
        assert exc.value.status_code == 409


class TestVisits:
    async def test_add_by_name_creates_the_place_with_the_given_kind(self, services):
        services.places.get_places.return_value = []
        services.places.create_place.return_value = _place(id=5, name="Museum Example", kind="museum")
        services.visits.create_visit.return_value = _visit()
        await run("travel_visit", "add", {
            "place": "Museum Example", "kind": "museum", "city": "Lisbon", "trip": "1", "date": "2031-12-18", "time": "10:00",
        }, services)
        place: PlaceCreate = services.places.create_place.await_args.args[0]
        assert (place.kind, place.city) == ("museum", "Lisbon")
        visit = services.visits.create_visit.await_args.args[0]
        assert (visit.place_id, visit.trip_id, visit.visit_date, visit.visit_time, visit.status) == (5, 1, date(2031, 12, 18), time(10, 0), "planned")

    async def test_add_reuses_a_known_place(self, services):
        services.places.get_places.return_value = [_place(id=5, name="Museum Example", kind="museum")]
        services.visits.create_visit.return_value = _visit()
        await run("travel_visit", "add", {"place": "museum example"}, services)
        services.places.create_place.assert_not_awaited()
        assert services.visits.create_visit.await_args.args[0].place_id == 5

    async def test_add_graded_but_planned_is_a_400(self, services):
        services.places.get_place.return_value = _place()
        with pytest.raises(HTTPException) as exc:
            await run("travel_visit", "add", {"place": "3", "grade": "4"}, services)
        assert exc.value.status_code == 400 and "visited" in exc.value.detail

    async def test_bad_time_is_a_400(self, services):
        services.places.get_place.return_value = _place()
        with pytest.raises(HTTPException) as exc:
            await run("travel_visit", "add", {"place": "3", "time": "evening"}, services)
        assert "HH:MM" in exc.value.detail

    async def test_visited_with_a_grade(self, services):
        services.visits.update_visit.return_value = _visit(status="visited", grade=5)
        result = await run("travel_visit", "visited", {"id": "11", "grade": "5", "notes": "Lovely"}, services)
        update = services.visits.update_visit.await_args.args[1]
        assert update.model_dump(exclude_unset=True) == {"status": "visited", "grade": 5, "notes": "Lovely"}
        assert "graded 5/5" in result["message"]

    async def test_missed_ignores_a_grade(self, services):
        services.visits.update_visit.return_value = _visit(status="missed")
        await run("travel_visit", "missed", {"id": "11", "grade": "3"}, services)
        assert services.visits.update_visit.await_args.args[1].model_dump(exclude_unset=True) == {"status": "missed"}

    async def test_list_resolves_the_trip_and_place(self, services):
        services.trips.get_trip.return_value = _trip()
        services.places.get_place.return_value = _place()
        services.visits.get_visits.return_value = [_visit()]
        result = await run("travel_visit", "list", {"trip": "1", "place": "3", "status": "planned", "no_trip": "false"}, services)
        f = services.visits.get_visits.await_args.args[0]
        assert (f.trip_id, f.place_id, f.status, f.no_trip) == (1, 3, "planned", False)
        assert result["visits"][0]["place"] == "Museum Example"

    async def test_update_moves_a_visit_to_another_place(self, services):
        services.places.get_places.return_value = [_place(id=8, name="Other Museum", kind="museum")]
        services.visits.update_visit.return_value = _visit()
        await run("travel_visit", "update", {"id": "11", "place": "Other Museum"}, services)
        assert services.visits.update_visit.await_args.args[1].place_id == 8

    async def test_delete_unknown(self, services):
        services.visits.delete_visit.return_value = False
        with pytest.raises(HTTPException) as exc:
            await run("travel_visit", "delete", {"id": "11"}, services)
        assert exc.value.status_code == 404


class TestLinks:
    @pytest.mark.parametrize("cmd_type,kind", [("travel_leg", "legs"), ("travel_stay", "stays"), ("travel_visit", "visits")])
    async def test_link_and_unlink(self, services, cmd_type, kind):
        services.links.link.return_value = LinkedTransactions(transactions=[], cost=Cost(total_eur="10.00", transaction_count=1))
        services.links.unlink.return_value = True
        linked = await run(cmd_type, "link", {"id": "4", "transaction_id": "9"}, services)
        services.links.link.assert_awaited_once_with(kind, 4, 9)
        assert linked["cost"]["total_eur"] == "10.00"
        assert "unlinked" in (await run(cmd_type, "unlink", {"id": "4", "transaction_id": "9"}, services))["message"]

    async def test_unlink_of_something_not_linked_is_a_400(self, services):
        services.links.unlink.return_value = False
        with pytest.raises(HTTPException) as exc:
            await run("travel_leg", "unlink", {"id": "4", "transaction_id": "9"}, services)
        assert exc.value.status_code == 400

    async def test_a_transfer_is_refused_with_a_400(self, services):
        services.links.link.side_effect = TransferNotLinkableError("Transfers can't be linked to a trip")
        with pytest.raises(HTTPException) as exc:
            await run("travel_leg", "link", {"id": "4", "transaction_id": "9"}, services)
        assert exc.value.status_code == 400

    async def test_unknown_target_is_a_404(self, services):
        services.links.link.side_effect = TravelNotFoundError("Transaction 9 not found")
        with pytest.raises(HTTPException) as exc:
            await run("travel_visit", "link", {"id": "4", "transaction_id": "9"}, services)
        assert exc.value.status_code == 404


async def test_unknown_group_and_command(services):
    with pytest.raises(HTTPException):
        await run("travel_boat", "list", {}, services)
    with pytest.raises(HTTPException):
        await run("travel_trip", "teleport", {}, services)


class TestToday:
    @staticmethod
    def _today():
        from app.features.travel.trips.today import TripToday

        return TripToday(trip_id=1, trip_name="Example trip", date=date(2031, 12, 18), timezone="UTC")

    async def test_defaults_to_the_ongoing_trip(self, services):
        services.trips.get_trips.return_value = [_trip()]
        services.trips.get_today.return_value = self._today()
        result = await run("travel_trip", "today", {}, services)
        assert services.trips.get_trips.await_args.args[0].status == "ongoing"
        assert result["trip_name"] == "Example trip"

    async def test_no_ongoing_trip_is_not_found(self, services):
        services.trips.get_trips.return_value = []
        with pytest.raises(HTTPException) as exc:
            await run("travel_trip", "today", {}, services)
        assert exc.value.status_code == 404

    async def test_a_named_trip_is_looked_up_by_name(self, services):
        services.trips.get_trips.return_value = [_trip()]
        services.trips.get_today.return_value = self._today()
        await run("travel_trip", "today", {"trip": "example"}, services)
        services.trips.get_today.assert_awaited_once_with(1)
