from datetime import date, datetime, time, timezone

from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.coverage_warnings import find_lodging_warnings, find_visit_warnings
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _dt(day, hour=0, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)


def _leg(id, origin, destination, departs, arrives, **kw):
    base = dict(
        id=id, trip_id=1, mode="flight", origin=origin, destination=destination, origin_code=None,
        destination_code=None, departs_at=departs, arrives_at=arrives, departs_tz="UTC", arrives_tz="UTC",
        carrier=None, number=None, booking_ref=None, booking_url=None, seat=None, notes=None,
        created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return LegRead(**base)


def _stay(id, check_in, check_out, city="Beta"):
    place = PlaceRead(
        id=1, kind="hotel", name="Hotel Example", city=city, country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, created_at=NOW, updated_at=NOW,
    )
    return StayRead(
        id=id, trip_id=1, place_id=1, place=place, check_in_at=check_in, check_out_at=check_out, timezone="UTC",
        booking_ref=None, booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _visit(id, day, at=None, city="Beta", status="planned"):
    place = VisitPlace(id=1, kind="restaurant", name="Cafe Example", city=city, maps_url=None, lat=None, lng=None)
    return VisitRead(
        id=id, place_id=1, place=place, trip_id=1, trip_name="T", status=status, visit_date=date(2026, 3, day) if day else None,
        visit_time=at, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


OUT = _leg(1, "Alpha", "Beta", _dt(10, 8), _dt(10, 10))
BACK = _leg(2, "Beta", "Alpha", _dt(14, 8), _dt(14, 10))


def _kinds(warnings):
    return [w.kind for w in warnings]


class TestUncoveredNight:
    def test_a_stay_covering_every_night_is_clean(self):
        assert find_lodging_warnings([OUT, BACK], [_stay(1, _dt(10, 14), _dt(14, 11))]) == []

    def test_lists_the_nights_without_a_stay_in_one_warning(self):
        warnings = find_lodging_warnings([OUT, BACK], [_stay(1, _dt(10, 14), _dt(12, 11))])
        assert _kinds(warnings) == ["uncovered_night"]
        assert "2 nights" in warnings[0].message and "12 Mar" in warnings[0].message and "13 Mar" in warnings[0].message

    def test_no_stays_at_all_still_flags_the_nights(self):
        assert _kinds(find_lodging_warnings([OUT, BACK], [])) == ["uncovered_night"]

    def test_a_day_trip_has_no_nights(self):
        day_trip = _leg(3, "Alpha", "Beta", _dt(10, 8), _dt(10, 10))
        back = _leg(4, "Beta", "Alpha", _dt(10, 20), _dt(10, 22))
        assert find_lodging_warnings([day_trip, back], []) == []

    def test_an_overnight_leg_covers_its_own_night(self):
        night_train = _leg(5, "Beta", "Gamma", _dt(12, 22), _dt(13, 6), mode="train")
        stays = [_stay(1, _dt(10, 14), _dt(12, 11)), _stay(2, _dt(13, 8), _dt(14, 8), city="Gamma")]
        legs = [OUT, night_train, _leg(6, "Gamma", "Alpha", _dt(14, 9), _dt(14, 11))]
        assert find_lodging_warnings(legs, stays) == []

    def test_no_legs_no_warning(self):
        assert find_lodging_warnings([], []) == []


class TestNoReturnLeg:
    def test_round_trip_is_clean(self):
        assert "no_return_leg" not in _kinds(find_lodging_warnings([OUT, BACK], [_stay(1, _dt(10, 14), _dt(14, 11))]))

    def test_last_leg_ending_elsewhere_is_flagged(self):
        onward = _leg(3, "Beta", "Gamma", _dt(14, 8), _dt(14, 10))
        warnings = find_lodging_warnings([OUT, onward], [_stay(1, _dt(10, 14), _dt(14, 11))])
        assert "no_return_leg" in _kinds(warnings)

    def test_a_single_leg_is_not_flagged(self):
        assert "no_return_leg" not in _kinds(find_lodging_warnings([OUT], [_stay(1, _dt(10, 14), _dt(14, 11))]))


class TestVisitWarnings:
    STAYS = [_stay(1, _dt(10, 14), _dt(14, 11))]

    def _run(self, visits, max_per_day=4):
        return find_visit_warnings(visits, [OUT, BACK], self.STAYS, max_per_day)

    def test_fine_visit_has_no_warning(self):
        assert self._run([_visit(1, 11, time(20, 0))]) == []

    def test_before_arrival(self):
        assert "visit_before_arrival" in _kinds(self._run([_visit(1, 10, time(9, 0))]))

    def test_after_last_departure(self):
        assert "visit_after_departure" in _kinds(find_visit_warnings(
            [_visit(1, 14, time(18, 0))], [OUT, BACK], [_stay(1, _dt(10, 14), _dt(14, 20))], 4))

    def test_during_a_leg(self):
        assert "visit_overlaps_leg" in _kinds(self._run([_visit(1, 14, time(9, 0))]))

    def test_no_stay_in_the_visits_city(self):
        assert "visit_without_stay" in _kinds(self._run([_visit(1, 11, time(12, 0), city="Gamma")]))

    def test_no_stays_at_all_skips_the_lodging_check(self):
        assert find_visit_warnings([_visit(1, 11, time(12, 0), city="Gamma")], [OUT, BACK], [], 4) == []

    def test_too_many_in_one_day_uses_the_limit(self):
        visits = [_visit(i, 11, time(9 + i, 0)) for i in range(1, 4)]
        assert "too_many_visits" in _kinds(self._run(visits, max_per_day=2))
        assert "too_many_visits" not in _kinds(self._run(visits, max_per_day=3))

    def test_visits_without_a_date_or_time_skip_the_time_checks(self):
        assert self._run([_visit(1, None), _visit(2, 11, None)]) == []

    def test_missed_visits_are_ignored(self):
        assert self._run([_visit(1, 10, time(9, 0), status="missed")]) == []
