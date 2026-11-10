from datetime import datetime, timezone

from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.timeline import build_timeline, find_warnings

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dt(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)


def _leg(id, origin, destination, departs, arrives, **kw):
    base = dict(
        id=id, trip_id=1, mode="flight", origin=origin, destination=destination, origin_code=None,
        destination_code=None, departs_at=departs, arrives_at=arrives, departs_tz="UTC", arrives_tz="Europe/Lisbon",
        carrier=None, number=None, booking_ref=None, booking_url=None, seat=None, notes=None,
        created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return LegRead(**base)


def _place(name="Hotel Example", city="Lisbon"):
    return PlaceRead(
        id=1, kind="hotel", name=name, city=city, country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _stay(id, check_in, check_out, city="Lisbon"):
    return StayRead(
        id=id, trip_id=1, place_id=1, place=_place(city=city), check_in_at=check_in, check_out_at=check_out,
        timezone="Europe/Lisbon", booking_ref=None, booking_url=None, notes=None, grade=None,
        created_at=NOW, updated_at=NOW,
    )


class TestBuildTimeline:
    def test_orders_legs_and_stay_events_chronologically(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        stay = _stay(5, _dt(2, 14), _dt(4, 10))
        items = build_timeline([leg], [stay])
        assert [i.kind for i in items] == ["leg", "check_in", "check_out"]

    def test_leg_links_have_directions_and_flight_lookup(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), carrier="XX", number="123")
        item = build_timeline([leg], [])[0]
        assert "travelmode=transit" in item.links["directions"]
        assert "XX+123" in item.links["check_flight"]

    def test_non_flight_has_no_flight_lookup(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), mode="train", carrier="XX", number="123")
        assert "check_flight" not in build_timeline([leg], [])[0].links

    def test_stay_links_cover_map_cafes_and_luggage(self):
        item = build_timeline([], [_stay(5, _dt(2, 14), _dt(4, 10))])[0]
        assert set(item.links) == {"map", "cafes", "luggage"}

    def test_local_time_uses_the_item_zone(self):
        leg = _leg(1, "Porto", "Lisbon", datetime(2026, 7, 1, 10, tzinfo=timezone.utc), _dt(2, 9), departs_tz="Europe/Stockholm")
        assert build_timeline([leg], [])[0].local.hour == 12


class TestWarnings:
    def test_no_data_no_warnings(self):
        assert find_warnings([], []) == []

    def test_long_wait_before_check_in(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 6), _dt(2, 8))
        stay = _stay(5, _dt(2, 15), _dt(4, 10))
        warnings = find_warnings([leg], [stay])
        assert [w.kind for w in warnings] == ["long_wait_before_check_in"]
        assert "7 h 00 min" in warnings[0].message

    def test_short_wait_is_fine(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 10), _dt(2, 12))
        assert find_warnings([leg], [_stay(5, _dt(2, 14), _dt(4, 10))]) == []

    def test_stay_in_another_city_is_not_matched(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 6), _dt(2, 8))
        assert find_warnings([leg], [_stay(5, _dt(2, 18), _dt(4, 10), city="Madrid")]) == []

    def test_arrival_after_check_out(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(4, 9), _dt(4, 12))
        warnings = find_warnings([leg], [_stay(5, _dt(2, 14), _dt(4, 10))])
        assert [w.kind for w in warnings] == ["arrives_after_check_out"]

    def test_tight_connection(self):
        a = _leg(1, "Porto", "Stockholm", _dt(2, 6), _dt(2, 9))
        b = _leg(2, "Stockholm", "Helsinki", _dt(2, 10), _dt(2, 12))
        warnings = find_warnings([a, b], [])
        assert [w.kind for w in warnings] == ["tight_connection"]
        assert warnings[0].leg_id == 2

    def test_comfortable_connection_is_fine(self):
        a = _leg(1, "Porto", "Stockholm", _dt(2, 6), _dt(2, 9))
        b = _leg(2, "Stockholm", "Helsinki", _dt(2, 12), _dt(2, 14))
        assert find_warnings([a, b], []) == []

    def test_different_places_are_not_a_connection(self):
        a = _leg(1, "Porto", "Stockholm", _dt(2, 6), _dt(2, 9))
        b = _leg(2, "Oslo", "Helsinki", _dt(2, 9, 30), _dt(2, 12))
        assert find_warnings([a, b], []) == []

    def test_overlapping_legs(self):
        a = _leg(1, "Porto", "Stockholm", _dt(2, 6), _dt(2, 9))
        b = _leg(2, "Stockholm", "Helsinki", _dt(2, 8), _dt(2, 12))
        assert [w.kind for w in find_warnings([a, b], [])] == ["overlapping_legs"]
