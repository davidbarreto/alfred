from datetime import date, datetime, time, timezone

from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.coverage_warnings import find_lodging_warnings, find_outside_dates_warnings, find_unpaid_leg_warnings, find_visit_warnings
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


class TestEventWarnings:
    from zoneinfo import ZoneInfo as _Z
    ZONE = _Z("Europe/Lisbon")
    TODAY = date(2026, 3, 10)

    @staticmethod
    def _v(id=1, day=18, at=time(20, 0), status="planned", event=None):
        v = _visit(id, day, at, status=status)
        return v.model_copy(update={"calendar_event_id": event})

    @staticmethod
    def _e(start, tz="Europe/Stockholm", **kw):
        from types import SimpleNamespace
        base = dict(start_datetime=start, timezone=tz, recurrence_rule=None, invitees=[], all_day=False)
        base.update(kw)
        return SimpleNamespace(**base)

    def _run(self, visits, events):
        from app.features.travel.trips.coverage_warnings import find_event_warnings
        return find_event_warnings(visits, events, self.TODAY, self.ZONE)

    def test_a_planned_timed_visit_without_an_event_is_flagged(self):
        assert _kinds(self._run([self._v()], {})) == ["no_calendar_event"]

    def test_past_untimed_visited_and_missed_visits_are_not_flagged(self):
        visits = [self._v(1, day=5), self._v(2, at=None), self._v(3, status="visited"), self._v(4, status="missed")]
        assert self._run(visits, {}) == []

    def test_a_matching_event_is_fine_compared_in_the_events_own_zone(self):
        # 19:00 Lisbon (UTC+0 in March) is 20:00 in Stockholm.
        event = self._e(datetime(2026, 3, 18, 19, 0))
        assert self._run([self._v(event=5)], {5: event}) == []

    def test_a_different_time_is_a_mismatch(self):
        event = self._e(datetime(2026, 3, 18, 18, 0))
        assert _kinds(self._run([self._v(event=5)], {5: event})) == ["linked_event_mismatch"]

    def test_a_different_day_is_a_mismatch(self):
        event = self._e(datetime(2026, 3, 19, 19, 0))
        assert _kinds(self._run([self._v(event=5)], {5: event})) == ["linked_event_mismatch"]

    def test_an_untouchable_event_gets_the_not_updated_warning_instead(self):
        event = self._e(datetime(2026, 3, 18, 18, 0), recurrence_rule="FREQ=WEEKLY")
        assert _kinds(self._run([self._v(event=5)], {5: event})) == ["linked_event_not_updated"]

    def test_a_linked_event_missing_from_the_local_copy_is_skipped(self):
        assert self._run([self._v(event=5)], {}) == []


class TestUnpaidLegWarnings:
    def _legs(self):
        return [_leg(1, "Alpha", "Beta", _dt(10, 8), _dt(10, 10)), _leg(2, "Beta", "Alpha", _dt(15, 8), _dt(15, 10))]

    def test_warns_about_legs_without_a_linked_charge_inside_the_window(self):
        warnings = find_unpaid_leg_warnings(self._legs(), {1}, date(2026, 3, 10), date(2026, 2, 20), 30)
        assert [(w.kind, w.leg_id) for w in warnings] == [("leg_not_paid", 2)]
        assert "Beta to Alpha" in warnings[0].message and "15 Mar" in warnings[0].message

    def test_silent_before_the_window_opens(self):
        assert find_unpaid_leg_warnings(self._legs(), set(), date(2026, 3, 10), date(2026, 1, 20), 30) == []

    def test_the_window_includes_its_first_day(self):
        assert len(find_unpaid_leg_warnings(self._legs(), set(), date(2026, 3, 10), date(2026, 2, 8), 30)) == 2

    def test_legs_already_travelled_are_not_flagged(self):
        warnings = find_unpaid_leg_warnings(self._legs(), set(), date(2026, 3, 10), date(2026, 3, 12), 30)
        assert [w.leg_id for w in warnings] == [2]

    def test_zero_days_turns_it_off(self):
        assert find_unpaid_leg_warnings(self._legs(), set(), date(2026, 3, 10), date(2026, 3, 9), 0) == []


class TestOutsideDatesWarnings:
    START, END = date(2026, 3, 10), date(2026, 3, 15)

    def test_nothing_inside_the_trip_is_flagged(self):
        legs = [_leg(1, "Alpha", "Beta", _dt(10, 8), _dt(10, 10)), _leg(2, "Beta", "Alpha", _dt(15, 8), _dt(15, 10))]
        stays = [_stay(1, _dt(10, 14), _dt(15, 10))]
        assert find_outside_dates_warnings(legs, stays, [_visit(1, 12)], self.START, self.END) == []

    def test_legs_stays_and_visits_outside_are_flagged(self):
        legs = [_leg(1, "Alpha", "Beta", _dt(9, 22), _dt(10, 2))]
        stays = [_stay(2, _dt(14, 14), _dt(16, 10))]
        visits = [_visit(3, 18), _visit(4, 9, status="missed"), _visit(5, None)]
        warnings = find_outside_dates_warnings(legs, stays, visits, self.START, self.END)
        assert [(w.kind, w.leg_id, w.stay_id, w.visit_id) for w in warnings] == [
            ("outside_trip_dates", 1, None, None), ("outside_trip_dates", None, 2, None), ("outside_trip_dates", None, None, 3),
        ]
        assert "Leg Alpha to Beta (09 Mar)" in warnings[0].message and "Cafe Example (18 Mar)" in warnings[2].message
