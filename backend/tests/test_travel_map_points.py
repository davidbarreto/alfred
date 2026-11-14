from datetime import date, datetime, time, timezone

from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.map_points import build_trip_map as _build
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
# The moment 'now' falls in the middle of the sample trip (2 to 9 March 2031).
MID_TRIP = datetime(2031, 3, 4, 12, tzinfo=timezone.utc)


def build_trip_map(trip_id, name, legs, stays, visits, now=MID_TRIP, scope="all"):
    return _build(trip_id, name, legs, stays, visits, now, scope)


def _leg(id, origin, destination, mode="flight", origin_code=None, destination_code=None, day=2):
    return LegRead(
        id=id, trip_id=1, mode=mode, origin=origin, destination=destination, origin_code=origin_code,
        destination_code=destination_code, departs_at=datetime(2031, 3, day, 8, tzinfo=timezone.utc),
        arrives_at=datetime(2031, 3, day, 9, tzinfo=timezone.utc), departs_tz="UTC", arrives_tz="UTC", carrier=None,
        number=None, booking_ref=None, booking_url=None, seat=None, notes=None, created_at=NOW, updated_at=NOW,
    )


def _place(id=1, name="Hotel Example", city="Lisbon", lat=None, lng=None, address=None):
    return PlaceRead(
        id=id, kind="hotel", name=name, city=city, country="Portugal", maps_url=None, lat=lat, lng=lng,
        address=address, notes=None, created_at=NOW, updated_at=NOW,
    )


def _stay(id, place, day_in, day_out):
    return StayRead(
        id=id, trip_id=1, place_id=place.id, place=place, check_in_at=datetime(2031, 3, day_in, 14, tzinfo=timezone.utc),
        check_out_at=datetime(2031, 3, day_out, 10, tzinfo=timezone.utc), timezone="UTC", booking_ref=None,
        booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _visit(id, place_id=30, name="Cafe Example", status="planned", day=date(2031, 3, 3)):
    return VisitRead(
        id=id, place_id=place_id, place=VisitPlace(id=place_id, kind="restaurant", name=name, city="Lisbon",
                                                  country="Portugal", maps_url=None, lat=None, lng=None),
        trip_id=1, trip_name="Example trip", status=status, visit_date=day, visit_time=time(20, 0), notes=None,
        grade=None, created_at=NOW, updated_at=NOW,
    )


class TestBuildTripMap:
    def test_stay_pin_uses_name_city_country_and_lists_dates(self):
        result = build_trip_map(1, "Trip", [], [_stay(1, _place(), 2, 4)], [])
        point = result.points[0]
        assert point.address == "Hotel Example, Lisbon, Portugal" and point.category == "lodging"
        assert point.description == "Stay 02 Mar - 04 Mar (2 nights)"

    def test_coordinates_win_then_address(self):
        with_coords = build_trip_map(1, "T", [], [_stay(1, _place(lat=38.7, lng=-9.1, address="Rua A 1"), 2, 4)], [])
        assert with_coords.points[0].address == "38.7,-9.1"
        with_address = build_trip_map(1, "T", [], [_stay(1, _place(address="Rua A 1"), 2, 4)], [])
        assert with_address.points[0].address == "Hotel Example, Rua A 1, Lisbon"

    def test_same_place_twice_is_one_pin_with_both_notes(self):
        visits = [_visit(1, 30, day=date(2031, 3, 3)), _visit(2, 30, day=date(2031, 3, 5))]
        points = build_trip_map(1, "T", [], [], visits).points
        assert len(points) == 1
        assert points[0].description == "Planned, 03 Mar 20:00; Planned, 05 Mar 20:00"

    def test_flight_airports_and_train_stations_are_pins_once_and_other_modes_are_not(self):
        legs = [
            _leg(1, "Porto", "Lisbon", origin_code="OPO", destination_code="LIS", day=2),
            _leg(2, "Lisbon", "Porto", origin_code="LIS", destination_code="OPO", day=9),
            _leg(3, "Porto", "Braga", mode="train"),
            _leg(4, "Porto", "Braga", mode="bus"),
        ]
        points = build_trip_map(1, "T", legs, [], []).points
        assert [(p.name, p.category) for p in points] == [
            ("OPO airport", "airport"), ("LIS airport", "airport"),
            ("Porto train station", "station"), ("Braga train station", "station"),
        ]

    def test_airport_without_code_falls_back_to_the_city(self):
        points = build_trip_map(1, "T", [_leg(1, "Porto", "Lisbon")], [], []).points
        assert [p.name for p in points] == ["Porto airport", "Lisbon airport"]

    def test_empty_trip_has_no_pins(self):
        assert build_trip_map(1, "T", [], [], []).points == []


class TestStatusAndScope:
    def test_status_follows_what_already_happened(self):
        visits = [_visit(1, 30, "Planned", "planned"), _visit(2, 31, "Done", "visited")]
        stay = _stay(1, _place(), 2, 4)
        points = {p.name: p.status for p in build_trip_map(1, "T", [], [stay], visits).points}
        assert points == {"Hotel Example": "visited", "Planned": "planned", "Done": "visited"}

    def test_a_stay_still_ahead_is_planned(self):
        early = datetime(2031, 3, 1, tzinfo=timezone.utc)
        assert build_trip_map(1, "T", [], [_stay(1, _place(), 2, 4)], [], now=early).points[0].status == "planned"

    def test_visited_scope_keeps_only_what_happened(self):
        visits = [_visit(1, 30, "Planned", "planned"), _visit(2, 31, "Done", "visited")]
        stay_later = _stay(2, _place(id=2, name="Hotel Later"), 8, 9)
        points = build_trip_map(1, "T", [], [_stay(1, _place(), 2, 4), stay_later], visits, scope="visited").points
        assert [p.name for p in points] == ["Hotel Example", "Done"]

    def test_visited_scope_describes_only_the_visit_that_happened(self):
        visits = [_visit(1, 30, "Cafe", "planned", day=date(2031, 3, 8)), _visit(2, 30, "Cafe", "visited", day=date(2031, 3, 3))]
        points = build_trip_map(1, "T", [], [], visits, scope="visited").points
        assert len(points) == 1 and points[0].description == "Visited, 03 Mar 20:00"

    def test_planned_scope_keeps_only_what_is_still_ahead(self):
        visits = [_visit(1, 30, "Planned", "planned"), _visit(2, 31, "Done", "visited"), _visit(3, 32, "Skipped", "missed")]
        stay_later = _stay(2, _place(id=2, name="Hotel Later"), 8, 9)
        points = build_trip_map(1, "T", [], [_stay(1, _place(), 2, 4), stay_later], visits, scope="planned").points
        assert {p.name: p.status for p in points} == {"Hotel Later": "planned", "Planned": "planned"}

    def test_missed_scope_keeps_only_missed_visits(self):
        visits = [_visit(1, 30, "Planned", "planned"), _visit(2, 31, "Done", "visited"), _visit(3, 32, "Skipped", "missed")]
        legs = [_leg(1, "Porto", "Lisbon", origin_code="OPO", destination_code="LIS")]
        points = build_trip_map(1, "T", legs, [_stay(1, _place(), 2, 4)], visits, scope="missed").points
        assert {p.name: p.status for p in points} == {"Skipped": "missed"}

    def test_all_scope_has_every_status(self):
        visits = [_visit(1, 30, "Planned", "planned"), _visit(2, 31, "Done", "visited"), _visit(3, 32, "Skipped", "missed")]
        assert {p.name: p.status for p in build_trip_map(1, "T", [], [], visits).points} == {
            "Planned": "planned", "Done": "visited", "Skipped": "missed",
        }

    def test_planned_scope_airports_only_for_flights_still_ahead(self):
        legs = [
            _leg(1, "Porto", "Lisbon", origin_code="OPO", destination_code="LIS", day=2),
            _leg(2, "Lisbon", "Faro", origin_code="LIS", destination_code="FAO", day=9),
        ]
        names = [p.name for p in build_trip_map(1, "T", legs, [], [], scope="planned").points]
        assert names == ["LIS airport", "FAO airport"]

    def test_a_place_both_done_and_missed_is_one_visited_pin_in_all(self):
        visits = [_visit(1, 30, "Cafe", "missed"), _visit(2, 30, "Cafe", "visited")]
        assert [p.status for p in build_trip_map(1, "T", [], [], visits).points] == ["visited"]

    def test_visited_scope_airports_only_for_flights_already_taken(self):
        legs = [
            _leg(1, "Porto", "Lisbon", origin_code="OPO", destination_code="LIS", day=2),
            _leg(2, "Lisbon", "Faro", origin_code="LIS", destination_code="FAO", day=9),
        ]
        names = [p.name for p in build_trip_map(1, "T", legs, [], [], scope="visited").points]
        assert names == ["OPO airport", "LIS airport"]
        all_points = build_trip_map(1, "T", legs, [], []).points
        assert {p.name: p.status for p in all_points} == {"OPO airport": "visited", "LIS airport": "visited", "FAO airport": "planned"}
