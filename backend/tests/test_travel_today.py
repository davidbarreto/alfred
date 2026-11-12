from datetime import date, datetime, time, timezone

from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.timeline import TimelineItem
from app.features.travel.trips.today import build_today
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _item(id, at):
    return TimelineItem(kind="leg", at=at, local=at.replace(tzinfo=None), timezone="UTC", title=f"Step {id}", ref_id=id)


def _visit(id, day, at=None, status="planned"):
    place = VisitPlace(id=id, kind="museum", name=f"Museum {id}", city="Beta", maps_url=None, lat=None, lng=None)
    return VisitRead(
        id=id, place_id=id, place=place, trip_id=1, trip_name="T", status=status, visit_date=day, visit_time=at,
        notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _trip(timeline=(), visits=(), stays=()):
    return TripDetail(
        id=1, name="Example trip", start_date=date(2026, 3, 10), end_date=date(2026, 3, 14), travelers=None,
        preferences=None, checklist_note_id=None, notes=None, default_tag_names=None, tags=[],
        created_at=NOW, updated_at=NOW, legs=[], stays=list(stays), timeline=list(timeline), warnings=[],
        visits=list(visits),
    )


def _at(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=timezone.utc)


class TestBuildToday:
    def test_next_item_is_the_first_one_not_yet_past_with_a_countdown(self):
        trip = _trip(timeline=[_item(1, _at(11, 8)), _item(2, _at(11, 12)), _item(3, _at(11, 18))])
        today = build_today(trip, _at(11, 10, 30), "UTC")
        assert today.next_item.ref_id == 2 and today.minutes_until_next == 90

    def test_no_next_item_after_the_last_step(self):
        today = build_today(_trip(timeline=[_item(1, _at(11, 8))]), _at(12, 8), "UTC")
        assert today.next_item is None and today.minutes_until_next is None

    def test_only_todays_visits_and_the_unmarked_count(self):
        trip = _trip(visits=[
            _visit(1, date(2026, 3, 11), time(9, 0), status="visited"),
            _visit(2, date(2026, 3, 11), time(15, 0)),
            _visit(3, date(2026, 3, 12), time(9, 0)),
        ])
        today = build_today(trip, _at(11, 10), "UTC")
        assert [v.id for v in today.visits] == [1, 2] and today.to_mark == 1

    def test_the_day_follows_the_zone_of_the_current_stay(self):
        from app.features.travel.places.schemas import PlaceRead
        from app.features.travel.stays.schemas import StayRead

        place = PlaceRead(id=1, kind="hotel", name="Hotel", city="Beta", country=None, maps_url=None, lat=None,
                          lng=None, address=None, notes=None, created_at=NOW, updated_at=NOW)
        stay = StayRead(id=1, trip_id=1, place_id=1, place=place, check_in_at=_at(10, 12), check_out_at=_at(14, 9),
                        timezone="Asia/Tokyo", booking_ref=None, booking_url=None, notes=None, grade=None,
                        created_at=NOW, updated_at=NOW)
        # 20:00 UTC on the 11th is already the 12th in Tokyo.
        today = build_today(_trip(stays=[stay]), _at(11, 20), "UTC")
        assert today.date == date(2026, 3, 12) and today.timezone == "Asia/Tokyo"
