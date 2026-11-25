from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError

from travel_city_helpers import city_ref
from app.features.location.places.tables import Place
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.schemas import LegCreate, LegUpdate
from app.features.travel.legs.service import LegService
from app.features.travel.places.schemas import TravelPlaceCreate, TravelPlaceFilters, TravelPlaceUpdate
from app.features.location.errors import LocationValidationError
from app.features.travel.places.service import TravelPlaceService
from app.features.travel.settings_schemas import TravelSettingsRead
from app.features.travel.stays.schemas import StayCreate, StayUpdate
from app.features.travel.stays.service import StayService
from app.features.travel.tags.schemas import TravelTagUpdate
from app.features.travel.tags.service import TravelTagNameTakenError, TravelTagService
from app.features.travel.tags.tables import TravelTag
from app.features.travel.trips.schemas import TripCreate, TripFilters, TripUpdate
from app.features.travel.trips.service import TripService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _trip(**kw):
    base = dict(
        id=1, name="Example trip", start_date=date(2026, 12, 17), end_date=date(2026, 12, 24), travelers=None,
        preferences=None, checklist_note_id=None, notes=None, default_tag_names=None, tags=[],
        home_city_id=None, home_address=None, airport_buffer_min=None, home_to_airport_min=None,
        created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _leg(**kw):
    base = dict(
        id=1, trip_id=1, mode="flight", origin="A", destination="B", origin_code=None, destination_code=None,
        departs_at=datetime(2026, 12, 17, 6, tzinfo=timezone.utc), arrives_at=datetime(2026, 12, 17, 9, tzinfo=timezone.utc),
        departs_tz="UTC", arrives_tz="Europe/Stockholm", carrier=None, number=None, booking_ref=None,
        booking_url=None, seat=None, notes=None, created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _place(**kw):
    base = dict(
        id=3, kind="hotel", name="Hotel Example", city=city_ref("Lisbon"), maps_url=None, latitude=None, longitude=None,
        address=None, notes=None, tags=[], created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _stay(**kw):
    base = dict(
        id=7, trip_id=1, place_id=3, place=_place(), check_in_at=datetime(2026, 12, 18, 14, tzinfo=timezone.utc),
        check_out_at=datetime(2026, 12, 20, 10, tzinfo=timezone.utc), timezone="Europe/Helsinki", booking_ref=None,
        booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def trips():
    svc = TripService(AsyncMock())
    svc._repo = AsyncMock()
    svc._city_repo = AsyncMock()
    svc._city_repo.get_city.return_value = None
    svc._tag_repo = AsyncMock()
    svc._leg_repo = AsyncMock()
    svc._stay_repo = AsyncMock()
    svc._visit_repo = AsyncMock()
    svc._visit_repo.get_trip_visits.return_value = []
    svc._link_repo = AsyncMock()
    svc._link_repo.get_linked_ids.return_value = set()
    svc._web_link_repo = AsyncMock()
    svc._web_link_repo.get_link_ids.return_value = []
    svc._checklist = AsyncMock()
    svc._checklist.is_pending.return_value = False
    svc.settings_service = AsyncMock()
    svc.settings_service.get.return_value = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=60)
    return svc


class TestTripService:
    async def test_create_resolves_tags_by_name(self, trips):
        trips._tag_repo.get_or_create_tags.return_value = [TravelTag(name="Family")]
        trips._repo.create_trip.return_value = _trip(tags=[TravelTag(name="Family")])
        result = await trips.create_trip(
            TripCreate(name="X", start_date=date(2026, 12, 17), end_date=date(2026, 12, 24), tags=["Family"])
        )
        trips._tag_repo.get_or_create_tags.assert_awaited_once_with(["family"])
        fields, tags = trips._repo.create_trip.await_args.args
        assert "tags" not in fields and tags[0].name == "Family"
        assert result.tags == ["Family"]

    async def test_update_unknown_trip(self, trips):
        trips._repo.get_trip.return_value = None
        assert await trips.update_trip(9, TripUpdate(name="x")) is None

    async def test_update_rejects_dates_out_of_order_against_stored_value(self, trips):
        trips._repo.get_trip.return_value = _trip()
        with pytest.raises(ValueError, match="end_date"):
            await trips.update_trip(1, TripUpdate(start_date=date(2027, 1, 1)))
        trips._repo.update_trip.assert_not_awaited()

    async def test_update_rejects_nulling_a_required_field(self, trips):
        trips._repo.get_trip.return_value = _trip()
        with pytest.raises(ValueError, match="name"):
            await trips.update_trip(1, TripUpdate.model_validate({"name": None}))

    async def test_update_without_tags_leaves_them_alone(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._repo.update_trip.return_value = _trip(name="New")
        await trips.update_trip(1, TripUpdate(name="New"))
        assert trips._repo.update_trip.await_args.args[2] is None
        trips._tag_repo.get_or_create_tags.assert_not_awaited()

    async def test_update_with_empty_tags_clears_them(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._tag_repo.get_or_create_tags.return_value = []
        trips._repo.update_trip.return_value = _trip()
        await trips.update_trip(1, TripUpdate(tags=[]))
        assert trips._repo.update_trip.await_args.args[2] == []

    async def test_list_passes_local_today(self, trips):
        trips._repo.get_trips.return_value = [_trip()]
        trips._repo.get_trip_locations.return_value = {}
        await trips.get_trips(TripFilters())
        assert isinstance(trips._repo.get_trips.await_args.args[1], date)

    async def test_list_carries_the_cities_and_countries_of_each_trip(self, trips):
        trips._repo.get_trips.return_value = [_trip(id=1), _trip(id=2)]
        trips._repo.get_trip_locations.return_value = {1: (["Alpha", "Beta"], ["Examplia"]), 2: ([], [])}
        found = await trips.get_trips(TripFilters())
        assert (found[0].cities, found[0].countries) == (["Alpha", "Beta"], ["Examplia"])
        assert (found[1].cities, found[1].countries) == ([], [])

    async def test_empty_list_skips_the_locations_query(self, trips):
        trips._repo.get_trips.return_value = []
        assert await trips.get_trips(TripFilters()) == []
        trips._repo.get_trip_locations.assert_not_awaited()

    async def test_locations_for_the_filters(self, trips):
        trips._repo.get_locations.return_value = (["Alpha"], ["Examplia"])
        found = await trips.get_locations()
        assert (found.cities, found.countries) == (["Alpha"], ["Examplia"])

    async def test_map_unknown_trip(self, trips):
        trips._repo.get_trip.return_value = None
        assert await trips.get_trip_map(9) is None

    async def test_map_includes_all_visits_even_after_the_trip(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = [_stay()]
        result = await trips.get_trip_map(1)
        assert [p.category for p in result.points] == ["lodging"]
        trips._visit_repo.get_trip_visits.assert_awaited_once_with(1)

    async def test_map_scope_visited_drops_stays_not_begun_yet(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = [_stay(check_in_at=datetime(2999, 1, 1, tzinfo=timezone.utc),
                                                         check_out_at=datetime(2999, 1, 3, tzinfo=timezone.utc))]
        assert (await trips.get_trip_map(1, "visited")).points == []
        assert len((await trips.get_trip_map(1)).points) == 1

    async def test_detail_combines_legs_stays_timeline_and_warnings(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = [_leg()]
        trips._stay_repo.get_stays.return_value = [_stay()]
        detail = await trips.get_trip_detail(1)
        assert len(detail.legs) == 1 and len(detail.stays) == 1
        # first leg is a flight departing 06:00: leave 3 h earlier
        assert [i.kind for i in detail.timeline] == ["leave_home", "leg", "arrival", "check_in", "check_out"]
        assert detail.leave_home_at == datetime(2026, 12, 17, 3, tzinfo=timezone.utc)
        assert detail.status in ("upcoming", "ongoing", "past")

    async def test_detail_uses_the_trips_own_home_values_over_the_settings(self, trips):
        trips._repo.get_trip.return_value = _trip(home_city_id=4, home_address="Rua Antiga 2", airport_buffer_min=60, home_to_airport_min=0)
        trips._city_repo.get_city.return_value = SimpleNamespace(
            id=4, name="Alpha", country=SimpleNamespace(id=1, name="Examplia", code=None),
        )
        trips._leg_repo.get_legs.return_value = [_leg()]
        trips._stay_repo.get_stays.return_value = [_stay()]
        detail = await trips.get_trip_detail(1)
        assert detail.leave_home_at == datetime(2026, 12, 17, 5, tzinfo=timezone.utc)  # 60 + 0 min before 06:00, not 180
        assert (detail.home.city.name, detail.home.address, detail.home.from_trip) == ("Alpha", "Rua Antiga 2", True)

    async def test_detail_home_follows_the_settings_when_the_trip_has_none(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = [_leg()]
        trips._stay_repo.get_stays.return_value = []
        detail = await trips.get_trip_detail(1)
        assert (detail.home.airport_buffer_min, detail.home.home_to_airport_min, detail.home.from_trip) == (120, 60, False)
        assert detail.home.city is None

    @freeze_time("2026-12-10 10:00:00")
    async def test_detail_warns_about_legs_without_a_linked_charge(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = [_leg()]
        trips._stay_repo.get_stays.return_value = [_stay()]
        detail = await trips.get_trip_detail(1)
        trips._link_repo.get_linked_ids.assert_any_await("legs", [1])
        assert [w.kind for w in detail.warnings if w.kind == "leg_not_paid"] == ["leg_not_paid"]
        trips._link_repo.get_linked_ids.return_value = {1}
        assert not [w for w in (await trips.get_trip_detail(1)).warnings if w.kind == "leg_not_paid"]

    @freeze_time("2026-12-10 10:00:00")
    async def test_detail_nudges_when_the_checklist_is_not_generated(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = []
        trips._checklist.is_pending.return_value = True
        detail = await trips.get_trip_detail(1)
        assert "checklist_not_generated" in [w.kind for w in detail.warnings]
        trips._checklist.is_pending.assert_awaited_once_with("Example trip")

    @freeze_time("2026-06-01 10:00:00")
    async def test_detail_does_not_check_the_checklist_far_ahead(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = []
        await trips.get_trip_detail(1)
        trips._checklist.is_pending.assert_not_awaited()

    @freeze_time("2026-12-10 10:00:00")
    async def test_detail_loads_the_wishlist_for_the_cities_of_an_upcoming_trip(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = [_stay()]
        trips._visit_repo.get_wishlist_in_cities.return_value = []
        detail = await trips.get_trip_detail(1)
        trips._visit_repo.get_wishlist_in_cities.assert_awaited_once_with(["Lisbon"])
        assert detail.ideas == []

    @freeze_time("2027-02-01 10:00:00")
    async def test_detail_of_an_ended_trip_has_no_ideas_and_skips_the_wishlist(self, trips):
        trips._repo.get_trip.return_value = _trip()
        trips._leg_repo.get_legs.return_value = []
        trips._stay_repo.get_stays.return_value = [_stay()]
        detail = await trips.get_trip_detail(1)
        trips._visit_repo.get_wishlist_in_cities.assert_not_awaited()
        assert detail.ideas == []

    async def test_detail_unknown_trip(self, trips):
        trips._repo.get_trip.return_value = None
        assert await trips.get_trip_detail(9) is None

    async def test_delete(self, trips):
        trips._repo.delete_trip.return_value = True
        assert await trips.delete_trip(1) is True


@pytest.fixture
def legs():
    svc = LegService(AsyncMock())
    svc._repo = AsyncMock()
    svc._trip_repo = AsyncMock()
    svc._city_repo = AsyncMock()
    svc._city_repo.find_unique_city_id.return_value = None
    return svc


class TestLegService:
    def _create(self):
        return LegCreate(
            trip_id=1, mode="flight", origin="A", destination="B", departs_at=datetime(2026, 12, 17, 6),
            arrives_at=datetime(2026, 12, 17, 10), departs_tz="UTC", arrives_tz="Europe/Stockholm",
        )

    async def test_create_needs_an_existing_trip(self, legs):
        legs._trip_repo.get_trip.return_value = None
        with pytest.raises(TravelNotFoundError):
            await legs.create_leg(self._create())
        legs._repo.create_leg.assert_not_awaited()

    async def test_create_stores_utc_instants(self, legs):
        legs._trip_repo.get_trip.return_value = _trip()
        legs._repo.create_leg.return_value = _leg()
        await legs.create_leg(self._create())
        stored = legs._repo.create_leg.await_args.args[0]
        assert stored["arrives_at"] == datetime(2026, 12, 17, 9, tzinfo=timezone.utc)

    async def test_create_matches_an_unsent_city_by_the_terminal_text(self, legs):
        legs._trip_repo.get_trip.return_value = _trip()
        legs._repo.create_leg.return_value = _leg()
        legs._city_repo.find_unique_city_id.side_effect = lambda text: {"A": 11}.get(text)
        await legs.create_leg(self._create())
        stored = legs._repo.create_leg.await_args.args[0]
        assert (stored["origin_city_id"], stored["destination_city_id"]) == (11, None)

    async def test_create_uses_a_sent_city_as_is_and_null_clears_the_match(self, legs):
        legs._trip_repo.get_trip.return_value = _trip()
        legs._repo.create_leg.return_value = _leg()
        legs._city_repo.find_unique_city_id.return_value = 11
        legs._city_repo.get_city.return_value = object()
        data = LegCreate(
            trip_id=1, mode="flight", origin="A", destination="B", departs_at=datetime(2026, 12, 17, 6),
            arrives_at=datetime(2026, 12, 17, 10), departs_tz="UTC", arrives_tz="UTC", origin_city_id=4, destination_city_id=None,
        )
        await legs.create_leg(data)
        stored = legs._repo.create_leg.await_args.args[0]
        assert (stored["origin_city_id"], stored["destination_city_id"]) == (4, None)

    async def test_create_with_an_unknown_city_id_is_not_found(self, legs):
        legs._trip_repo.get_trip.return_value = _trip()
        legs._city_repo.get_city.return_value = None
        data = LegCreate(
            trip_id=1, mode="flight", origin="A", destination="B", departs_at=datetime(2026, 12, 17, 6),
            arrives_at=datetime(2026, 12, 17, 10), departs_tz="UTC", arrives_tz="UTC", origin_city_id=99,
        )
        with pytest.raises(TravelNotFoundError):
            await legs.create_leg(data)
        legs._repo.create_leg.assert_not_awaited()

    async def test_update_rematches_the_end_whose_text_changed(self, legs):
        leg = _leg()
        legs._repo.get_leg.return_value = leg
        legs._repo.update_leg.return_value = leg
        legs._city_repo.find_unique_city_id.return_value = 12
        await legs.update_leg(1, LegUpdate(destination="Gamma"))
        changes = legs._repo.update_leg.await_args.args[1]
        assert changes["destination_city_id"] == 12 and "origin_city_id" not in changes

    async def test_update_that_sends_the_city_keeps_it_even_when_the_text_changes(self, legs):
        leg = _leg()
        legs._repo.get_leg.return_value = leg
        legs._repo.update_leg.return_value = leg
        legs._city_repo.get_city.return_value = object()
        legs._city_repo.find_unique_city_id.return_value = 12
        await legs.update_leg(1, LegUpdate(origin="Gamma", origin_city_id=4))
        assert legs._repo.update_leg.await_args.args[1]["origin_city_id"] == 4

    async def test_update_with_a_null_city_clears_it(self, legs):
        leg = _leg()
        legs._repo.get_leg.return_value = leg
        legs._repo.update_leg.return_value = leg
        await legs.update_leg(1, LegUpdate.model_validate({"origin_city_id": None}))
        assert legs._repo.update_leg.await_args.args[1]["origin_city_id"] is None

    async def test_update_without_a_text_or_city_change_leaves_the_cities_alone(self, legs):
        leg = _leg()
        legs._repo.get_leg.return_value = leg
        legs._repo.update_leg.return_value = leg
        await legs.update_leg(1, LegUpdate(seat="1A"))
        changes = legs._repo.update_leg.await_args.args[1]
        assert "origin_city_id" not in changes and "destination_city_id" not in changes
        legs._city_repo.find_unique_city_id.assert_not_awaited()

    async def test_update_reads_naive_time_in_the_stored_zone(self, legs):
        leg = _leg()
        legs._repo.get_leg.return_value = leg
        legs._repo.update_leg.return_value = leg
        await legs.update_leg(1, LegUpdate(arrives_at=datetime(2026, 12, 17, 12)))
        changes = legs._repo.update_leg.await_args.args[1]
        assert changes["arrives_at"] == datetime(2026, 12, 17, 11, tzinfo=timezone.utc)

    async def test_update_rejects_arrival_before_stored_departure(self, legs):
        legs._repo.get_leg.return_value = _leg()
        with pytest.raises(ValueError, match="arrives_at"):
            await legs.update_leg(1, LegUpdate(arrives_at=datetime(2026, 12, 17, 5)))

    async def test_update_unknown_leg(self, legs):
        legs._repo.get_leg.return_value = None
        assert await legs.update_leg(1, LegUpdate(seat="1A")) is None

    async def test_delete_unknown_leg(self, legs):
        legs._repo.get_leg.return_value = None
        assert await legs.delete_leg(1) is False


@pytest.fixture
def stays():
    svc = StayService(AsyncMock())
    svc._repo = AsyncMock()
    svc._trip_repo = AsyncMock()
    svc._place_repo = AsyncMock()
    return svc


class TestStayService:
    def _create(self, **kw):
        return StayCreate(
            place_id=3, trip_id=kw.get("trip_id", 1), check_in_at=datetime(2026, 12, 18, 16),
            check_out_at=datetime(2026, 12, 20, 12), timezone="Europe/Helsinki",
        )

    async def test_create_needs_an_existing_place(self, stays):
        stays._trip_repo.get_trip.return_value = _trip()
        stays._place_repo.get_place.return_value = None
        with pytest.raises(TravelNotFoundError, match="Place"):
            await stays.create_stay(self._create())

    async def test_create_without_trip_skips_the_trip_check(self, stays):
        stays._place_repo.get_place.return_value = _place()
        stays._repo.create_stay.return_value = _stay(trip_id=None)
        result = await stays.create_stay(self._create(trip_id=None))
        stays._trip_repo.get_trip.assert_not_awaited()
        assert result.trip_id is None

    async def test_update_converts_with_the_new_zone(self, stays):
        stay = _stay()
        stays._repo.get_stay.return_value = stay
        stays._repo.update_stay.return_value = stay
        await stays.update_stay(7, StayUpdate(timezone="UTC", check_out_at=datetime(2026, 12, 21, 10)))
        changes = stays._repo.update_stay.await_args.args[1]
        assert changes["check_out_at"] == datetime(2026, 12, 21, 10, tzinfo=timezone.utc)

    async def test_update_rejects_check_out_before_check_in(self, stays):
        stays._repo.get_stay.return_value = _stay()
        with pytest.raises(ValueError, match="check_out_at"):
            await stays.update_stay(7, StayUpdate(check_out_at=datetime(2026, 12, 1)))

    async def test_update_rejects_nulling_place(self, stays):
        stays._repo.get_stay.return_value = _stay()
        with pytest.raises(ValueError, match="place_id"):
            await stays.update_stay(7, StayUpdate.model_validate({"place_id": None}))


@pytest.fixture
def places():
    base = AsyncMock()
    base.add.return_value = Place(id=3)
    svc = TravelPlaceService(AsyncMock(), base)
    svc._repo = AsyncMock()
    svc._repo.get_grades.return_value = {}
    svc._repo.get_place.return_value = _place()
    svc._city_repo = AsyncMock()
    svc._cities = AsyncMock()
    svc._tag_repo = AsyncMock()
    svc._tag_repo.get_or_create_tags.return_value = []
    return svc


class TestPlaceService:
    async def test_locations_for_the_filters(self, places):
        places._repo.get_locations.return_value = (["Alpha"], ["Examplia"])
        found = await places.get_locations()
        assert (found.cities, found.countries) == (["Alpha"], ["Examplia"])

    async def test_create_goes_through_the_base_place_with_its_tags(self, places):
        places._tag_repo.get_or_create_tags.return_value = [TravelTag(name="would return")]

        result = await places.create_place(TravelPlaceCreate(kind="hotel", name="Hotel Example", city_id=5, tags=["Would return"]))

        sent = places._places.add.await_args.args[0]
        assert (sent.kind, sent.name, sent.city_id) == ("hotel", "Hotel Example", 5)
        assert [t.name for t in places._places.add.return_value.tags] == ["would return"]
        places._places.saved.assert_awaited_once_with(3, created=True)
        assert result.name == "Hotel Example"

    async def test_create_by_names_resolves_the_country_and_city(self, places):
        places._cities.resolve_country.return_value = SimpleNamespace(id=2)
        places._cities.resolve_city.return_value = SimpleNamespace(id=8)
        await places.create_place(TravelPlaceCreate(kind="hotel", name="Hotel Example", city="Alpha", country="Examplia", country_code="EX"))
        places._cities.resolve_country.assert_awaited_once_with("Examplia", "EX")
        assert places._places.add.await_args.args[0].city_id == 8

    async def test_create_with_an_unknown_city_id_is_not_found(self, places):
        places._city_repo.get_city.return_value = None
        with pytest.raises(TravelNotFoundError):
            await places.create_place(TravelPlaceCreate(kind="hotel", name="Hotel Example", city_id=99))
        places._places.add.assert_not_awaited()

    async def test_update_with_a_lone_city_keeps_the_current_country(self, places):
        places._cities.resolve_country.return_value = SimpleNamespace(id=2)
        places._cities.resolve_city.return_value = SimpleNamespace(id=8)
        await places.update_place(3, TravelPlaceUpdate(city="Alpha"))
        places._cities.resolve_country.assert_awaited_once_with("Testland", None)
        assert places._places.update.await_args.args[1].model_dump(exclude_unset=True) == {"city_id": 8}

    async def test_update_with_a_lone_country_keeps_the_current_city_name(self, places):
        places._cities.resolve_country.return_value = SimpleNamespace(id=2)
        places._cities.resolve_city.return_value = SimpleNamespace(id=8)
        await places.update_place(3, TravelPlaceUpdate(country="Newland"))
        assert places._cities.resolve_city.await_args.args[0] == "Lisbon"

    async def test_update_without_a_city_field_does_not_touch_the_city(self, places):
        await places.update_place(3, TravelPlaceUpdate(name="Renamed"))
        places._cities.resolve_city.assert_not_awaited()
        assert places._places.update.await_args.args[1].model_dump(exclude_unset=True) == {"name": "Renamed"}

    async def test_tags_alone_leave_the_base_place_untouched(self, places):
        await places.update_place(3, TravelPlaceUpdate(tags=["Family"]))
        places._places.update.assert_not_awaited()
        places._repo.set_tags.assert_awaited_once()

    async def test_nulling_name_is_refused_by_the_base_place(self, places):
        places._places.update.side_effect = LocationValidationError("name cannot be cleared")
        with pytest.raises(LocationValidationError, match="name"):
            await places.update_place(3, TravelPlaceUpdate.model_validate({"name": None}))

    async def test_update_unknown_is_none(self, places):
        places._repo.get_place.return_value = None
        assert await places.update_place(3, TravelPlaceUpdate(name="Renamed")) is None

    async def test_list(self, places):
        places._repo.get_places.return_value = [_place()]
        assert len(await places.get_places(TravelPlaceFilters())) == 1


@pytest.fixture
def tags():
    svc = TravelTagService(AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestTagService:
    async def test_rename_clash(self, tags):
        tags._repo.get_tag_by_name.return_value = TravelTag(id=2, name="family")
        with pytest.raises(TravelTagNameTakenError):
            await tags.rename_tag(1, TravelTagUpdate(name="Family"))

    async def test_rename_own_case(self, tags):
        tags._repo.get_tag_by_name.return_value = TravelTag(id=1, name="family")
        tags._repo.rename_tag.return_value = TravelTag(id=1, name="Family")
        assert (await tags.rename_tag(1, TravelTagUpdate(name="Family"))).name == "Family"

    async def test_rename_race(self, tags):
        tags._repo.get_tag_by_name.return_value = None
        tags._repo.rename_tag.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(TravelTagNameTakenError):
            await tags.rename_tag(1, TravelTagUpdate(name="x"))

    async def test_usage_counts_trips(self, tags):
        tags._repo.get_tags_with_usage.return_value = [(TravelTag(id=1, name="Family"), 2, 3)]
        usage = (await tags.get_tags())[0]
        assert (usage.trip_count, usage.place_count) == (2, 3)

    async def test_delete_unknown(self, tags):
        tags._repo.delete_tag.return_value = False
        assert await tags.delete_tag(1) is False
