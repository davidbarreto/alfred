from datetime import date, datetime, timezone

from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.ideas import OTHER_CITY, build_ideas
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _stay(id, city, day):
    place = PlaceRead(
        id=id, kind="hotel", name=f"Hotel {city}", city=city, country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, created_at=NOW, updated_at=NOW,
    )
    return StayRead(
        id=id, trip_id=1, place_id=id, place=place, check_in_at=datetime(2026, 3, day, 14, tzinfo=timezone.utc),
        check_out_at=datetime(2026, 3, day + 2, 10, tzinfo=timezone.utc), timezone="UTC", booking_ref=None,
        booking_url=None, notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )


def _visit(id, city, day=None, trip_id=1, status="planned"):
    place = VisitPlace(id=id, kind="museum", name=f"Museum {id}", city=city, maps_url=None, lat=None, lng=None)
    return VisitRead(
        id=id, place_id=id, place=place, trip_id=trip_id, trip_name=None, status=status,
        visit_date=date(2026, 3, day) if day else None, visit_time=None, notes=None, grade=None,
        created_at=NOW, updated_at=NOW,
    )


STAYS = [_stay(1, "Alpha", 10), _stay(2, "Beta", 12)]


class TestBuildIdeas:
    def test_groups_undated_planned_visits_by_stay_city_in_stay_order(self):
        ideas = build_ideas([_visit(1, "Beta"), _visit(2, "alpha")], [], STAYS)
        assert [(g.city, [v.id for v in g.visits]) for g in ideas] == [("Alpha", [2]), ("Beta", [1])]

    def test_dated_visited_and_missed_visits_are_not_ideas(self):
        trip = [_visit(1, "Alpha", day=11), _visit(2, "Alpha", status="visited"), _visit(3, "Alpha", status="missed")]
        assert build_ideas(trip, [], STAYS) == []

    def test_wishlist_visits_count_only_in_a_stay_city(self):
        wishlist = [_visit(5, "Alpha", trip_id=None), _visit(6, "Gamma", trip_id=None)]
        ideas = build_ideas([], wishlist, STAYS)
        assert [(g.city, [v.id for v in g.visits]) for g in ideas] == [("Alpha", [5])]

    def test_trip_visit_outside_every_stay_city_goes_under_other_places(self):
        ideas = build_ideas([_visit(1, "Gamma"), _visit(2, None)], [], STAYS)
        assert [(g.city, [v.id for v in g.visits]) for g in ideas] == [(OTHER_CITY, [1, 2])]

    def test_nothing_to_suggest(self):
        assert build_ideas([], [], STAYS) == []
