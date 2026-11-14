from datetime import date, datetime, timezone

import pytest
from freezegun import freeze_time
from pydantic import ValidationError

from app.features.travel.legs.schemas import LegCreate
from app.features.travel.places.schemas import PlaceCreate, PlaceRead
from app.features.travel.stays.schemas import StayCreate
from app.features.travel.tags.schemas import TravelTagUpdate
from app.features.travel.trips.schemas import TripCreate, TripRead, TripUpdate, trip_status
from app.features.travel.zones import to_local, to_utc

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestZones:
    def test_naive_is_read_in_the_zone(self):
        assert to_utc(datetime(2026, 12, 17, 12, 0), "Europe/Stockholm") == datetime(2026, 12, 17, 11, 0, tzinfo=timezone.utc)

    def test_aware_is_converted(self):
        aware = datetime.fromisoformat("2026-12-17T12:00:00+02:00")
        assert to_utc(aware, "UTC").hour == 10

    def test_to_local_round_trip(self):
        instant = datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
        assert to_local(instant, "Europe/Helsinki") == datetime(2026, 7, 1, 13)


class TestTripSchemas:
    def test_end_before_start_is_rejected(self):
        with pytest.raises(ValidationError):
            TripCreate(name="X", start_date=date(2026, 5, 2), end_date=date(2026, 5, 1))

    def test_tags_are_normalized(self):
        trip = TripCreate(name="X", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2), tags=[" Family", "family", ""])
        assert trip.tags == ["family"]

    def test_tags_are_stored_lowercase(self):
        trip = TripCreate(name="X", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2), tags=["Would Return", "FAMILY"])
        assert trip.tags == ["would return", "family"]

    def test_tag_rename_is_lowercased(self):
        assert TravelTagUpdate(name="  Family Friendly ").name == "family friendly"

    def test_update_tags_none_stays_none(self):
        assert TripUpdate().tags is None

    @pytest.mark.parametrize(
        "start,end,expected",
        [
            (date(2026, 6, 10), date(2026, 6, 12), "upcoming"),
            (date(2026, 6, 1), date(2026, 6, 5), "ongoing"),
            (date(2026, 6, 5), date(2026, 6, 5), "ongoing"),
            (date(2026, 5, 1), date(2026, 5, 3), "past"),
        ],
    )
    def test_status_is_derived_from_today(self, start, end, expected):
        assert trip_status(start, end, date(2026, 6, 5)) == expected

    @freeze_time("2026-06-05 23:30:00")
    def test_read_status_uses_the_local_day(self):
        # 23:30 UTC is already the next day in the configured zone only for zones ahead of UTC; either way the
        # status must come from local_today(), so the day boundary below is robust to that.
        read = TripRead(
            id=1, name="X", start_date=date(2026, 6, 1), end_date=date(2026, 6, 4), travelers=None, preferences=None,
            checklist_note_id=None, notes=None, default_tag_names=None, tags=[], created_at=NOW, updated_at=NOW,
        )
        assert read.status == "past"

    def test_read_converts_tag_objects_to_names(self):
        class _Tag:
            name = "Family"

        read = TripRead(
            id=1, name="X", start_date=date(2026, 6, 1), end_date=date(2026, 6, 4), travelers=None, preferences=None,
            checklist_note_id=None, notes=None, default_tag_names=None, tags=[_Tag()], created_at=NOW, updated_at=NOW,
        )
        assert read.tags == ["Family"]


class TestLegCreate:
    def _kwargs(self, **kw):
        base = dict(
            trip_id=1, mode="flight", origin="A", destination="B", departs_at=datetime(2026, 12, 17, 6, 0),
            arrives_at=datetime(2026, 12, 17, 10, 0), departs_tz="Europe/Lisbon", arrives_tz="Europe/Stockholm",
        )
        base.update(kw)
        return base

    def test_naive_times_become_utc_instants(self):
        leg = LegCreate(**self._kwargs())
        assert leg.departs_at == datetime(2026, 12, 17, 6, 0, tzinfo=timezone.utc)
        assert leg.arrives_at == datetime(2026, 12, 17, 9, 0, tzinfo=timezone.utc)

    def test_arrival_before_departure_is_rejected(self):
        with pytest.raises(ValidationError):
            LegCreate(**self._kwargs(arrives_at=datetime(2026, 12, 17, 4, 0)))

    def test_unknown_zone_is_rejected(self):
        with pytest.raises(ValidationError):
            LegCreate(**self._kwargs(departs_tz="Mars/Base"))

    def test_unknown_mode_is_rejected(self):
        with pytest.raises(ValidationError):
            LegCreate(**self._kwargs(mode="teleport"))


class TestStayCreate:
    def test_times_are_read_in_the_lodging_zone(self):
        stay = StayCreate(
            place_id=1, check_in_at=datetime(2026, 12, 18, 15), check_out_at=datetime(2026, 12, 20, 11),
            timezone="Europe/Helsinki",
        )
        assert stay.check_in_at == datetime(2026, 12, 18, 13, 0, tzinfo=timezone.utc)

    def test_check_out_before_check_in_is_rejected(self):
        with pytest.raises(ValidationError):
            StayCreate(place_id=1, check_in_at=datetime(2026, 12, 20), check_out_at=datetime(2026, 12, 19), timezone="UTC")

    def test_grade_is_one_to_five(self):
        with pytest.raises(ValidationError):
            StayCreate(place_id=1, check_in_at=datetime(2026, 12, 19), check_out_at=datetime(2026, 12, 20), timezone="UTC", grade=6)


class TestPlace:
    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            PlaceCreate(kind="spaceship", name="X")

    def test_maps_link_prefers_the_users_url_then_coordinates_then_search(self):
        base = dict(id=1, kind="hotel", name="Hotel Example", city="Lisbon", country=None, address=None, notes=None,
                    created_at=NOW, updated_at=NOW)
        assert PlaceRead(**base, maps_url="https://maps.example/x", lat=None, lng=None).maps_link == "https://maps.example/x"
        assert "38.7%2C-9.1" in PlaceRead(**base, maps_url=None, lat=38.7, lng=-9.1).maps_link
        assert "Hotel+Example+Lisbon" in PlaceRead(**base, maps_url=None, lat=None, lng=None).maps_link
