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
        assert [i.kind for i in items] == ["leg", "arrival", "check_in", "check_out"]

    def test_arrival_item_uses_arrival_time_and_zone(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        arrival = next(i for i in build_timeline([leg], []) if i.kind == "arrival")
        assert arrival.at == _dt(2, 9)
        assert arrival.timezone == "Europe/Lisbon"
        assert arrival.title == "Arrive: Lisbon"

    def test_flight_has_flight_lookup(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), carrier="XX", number="123")
        assert "XX+123" in build_timeline([leg], [])[0].links["check_flight"]

    def test_non_flight_directions_run_between_its_ends_in_three_modes(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), mode="train")
        links = build_timeline([leg], [])[0].links
        assert "travelmode=transit" in links["directions"] and "origin=Porto" in links["directions"]
        assert "travelmode=driving" in links["drive"] and "travelmode=walking" in links["walk"]

    def test_first_flight_directions_go_from_home_to_the_origin_airport(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), origin_code="OPO")
        item = build_timeline([leg], [], home_address="Rua Exemplo 1, Porto")[0]
        assert "origin=Rua+Exemplo+1%2C+Porto" in item.links["directions"]
        assert "destination=OPO+airport" in item.links["directions"]
        assert item.transfer_label == "Home \u2192 OPO airport"

    def test_first_flight_without_home_address_has_no_directions(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        item = build_timeline([leg], [])[0]
        assert "directions" not in item.links and item.transfer_label is None

    def test_later_flight_without_a_stay_has_no_directions(self):
        first = _leg(1, "Porto", "Madrid", _dt(2, 8), _dt(2, 9))
        second = _leg(2, "Madrid", "Lisbon", _dt(2, 12), _dt(2, 13))
        item = next(i for i in build_timeline([first, second], [], home_address="Home") if i.kind == "leg" and i.ref_id == 2)
        assert "directions" not in item.links

    def test_flight_leaving_a_hotel_directions_start_at_the_hotel(self):
        leg = _leg(1, "Lisbon", "Porto", _dt(5, 18), _dt(5, 19), origin_code="LIS")
        item = next(i for i in build_timeline([leg], [_stay(5, _dt(2, 14), _dt(5, 10))]) if i.kind == "leg")
        assert "origin=Hotel+Example+Lisbon" in item.links["directions"]
        assert "destination=LIS+airport" in item.links["directions"]
        assert item.transfer_label == "Hotel Example \u2192 LIS airport"

    def test_arrival_directions_go_from_the_airport_to_the_hotel(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), destination_code="LIS")
        arrival = next(i for i in build_timeline([leg], [_stay(5, _dt(2, 14), _dt(4, 10))]) if i.kind == "arrival")
        assert "origin=LIS+airport" in arrival.links["directions"]
        assert "destination=Hotel+Example+Lisbon" in arrival.links["directions"]
        assert arrival.transfer_label == "LIS airport \u2192 Hotel Example"

    def test_arrival_without_a_stay_has_no_transfer(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        arrival = next(i for i in build_timeline([leg], []) if i.kind == "arrival")
        assert arrival.transfer_label is None and "directions" not in arrival.links

    def test_hotel_coordinates_win_over_the_name(self):
        stay = _stay(5, _dt(2, 14), _dt(4, 10))
        stay.place.lat, stay.place.lng = 38.7, -9.1
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        arrival = next(i for i in build_timeline([leg], [stay]) if i.kind == "arrival")
        assert "destination=38.7%2C-9.1" in arrival.links["directions"]

    def test_warning_rows_are_flagged(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9))
        stay = _stay(5, _dt(2, 20), _dt(4, 10))
        warnings = find_warnings([leg], [stay])
        items = build_timeline([leg], [stay], warnings=warnings)
        flagged = {i.kind for i in items if i.warnings}
        assert flagged == {"arrival", "check_in"}
        assert next(i for i in items if i.kind == "arrival").warnings == [warnings[0].message]

    def test_tight_connection_flags_the_departing_leg(self):
        first = _leg(1, "Porto", "Madrid", _dt(2, 8), _dt(2, 9))
        second = _leg(2, "Madrid", "Lisbon", _dt(2, 9, 30), _dt(2, 11))
        items = build_timeline([first, second], [], warnings=find_warnings([first, second], []))
        assert [(i.kind, i.ref_id) for i in items if i.warnings] == [("leg", 2)]

    def test_non_flight_has_no_flight_lookup(self):
        leg = _leg(1, "Porto", "Lisbon", _dt(2, 8), _dt(2, 9), mode="train", carrier="XX", number="123")
        assert "check_flight" not in build_timeline([leg], [])[0].links

    def test_stay_links_cover_map_cafes_and_luggage(self):
        item = build_timeline([], [_stay(5, _dt(2, 14), _dt(4, 10))])[0]
        assert set(item.links) == {"map", "cafes", "luggage"}

    def test_local_time_uses_the_item_zone(self):
        leg = _leg(1, "Porto", "Lisbon", datetime(2026, 7, 1, 10, tzinfo=timezone.utc), _dt(2, 9), departs_tz="Europe/Stockholm")
        assert next(i for i in build_timeline([leg], []) if i.kind == "leg").local.hour == 12


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
