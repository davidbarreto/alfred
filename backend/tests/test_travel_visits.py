from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from pydantic import ValidationError

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.places.schemas import PlaceCreate, PlaceFilters, PlaceUpdate
from app.features.travel.places.service import PlaceService
from app.features.travel.tags.tables import TravelTag
from app.features.travel.trips.service import TripService
from app.features.travel.settings_schemas import TravelSettingsRead
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitUpdate
from app.features.travel.visits.service import VisitService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _place(**kw):
    base = dict(
        id=3, kind="restaurant", name="Cafe Example", city="Lisbon", country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, tags=[TravelTag(name="Would return")], created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _visit(**kw):
    base = dict(
        id=11, place_id=3, place=_place(), trip_id=1, trip_name="Example trip", status="planned",
        visit_date=date(2026, 12, 18), visit_time=time(20, 0), notes=None, grade=None, created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestVisitSchemas:
    def test_grade_needs_a_visited_status(self):
        with pytest.raises(ValidationError, match="visited"):
            VisitCreate(place_id=1, status="missed", grade=3)
        assert VisitCreate(place_id=1, status="visited", grade=3).grade == 3

    def test_update_allows_partial_bodies(self):
        assert VisitUpdate(notes="x").model_dump(exclude_unset=True) == {"notes": "x"}

    def test_filters_have_plain_defaults(self):
        f = VisitFilters()
        assert (f.trip_id, f.no_trip, f.limit, f.offset) == (None, False, 100, 0)


@pytest.fixture
def visits():
    svc = VisitService(AsyncMock())
    svc._repo = AsyncMock()
    svc._trip_repo = AsyncMock()
    svc._place_repo = AsyncMock()
    return svc


class TestVisitService:
    async def test_create_checks_the_place(self, visits):
        visits._place_repo.get_place.return_value = None
        with pytest.raises(TravelNotFoundError, match="Place"):
            await visits.create_visit(VisitCreate(place_id=3))

    async def test_create_without_trip_skips_the_trip_check(self, visits):
        visits._place_repo.get_place.return_value = _place()
        visits._repo.create_visit.return_value = _visit(trip_id=None, trip_name=None)
        result = await visits.create_visit(VisitCreate(place_id=3))
        visits._trip_repo.get_trip.assert_not_awaited()
        assert result.trip_id is None and result.place.maps_link.startswith("https://")

    async def test_marking_visited_with_a_grade(self, visits):
        visits._repo.get_visit.return_value = _visit()
        visits._repo.update_visit.return_value = _visit(status="visited", grade=5)
        await visits.update_visit(11, VisitUpdate(status="visited", grade=5))
        assert visits._repo.update_visit.await_args.args[1] == {"status": "visited", "grade": 5}

    async def test_grading_a_planned_visit_is_rejected(self, visits):
        visits._repo.get_visit.return_value = _visit()
        with pytest.raises(ValueError, match="visited"):
            await visits.update_visit(11, VisitUpdate(grade=4))

    async def test_moving_a_graded_visit_back_to_missed_drops_the_grade(self, visits):
        visits._repo.get_visit.return_value = _visit(status="visited", grade=4)
        visits._repo.update_visit.return_value = _visit(status="missed")
        await visits.update_visit(11, VisitUpdate(status="missed"))
        assert visits._repo.update_visit.await_args.args[1]["grade"] is None

    async def test_grade_and_non_visited_status_together_is_a_contradiction(self, visits):
        visits._repo.get_visit.return_value = _visit(status="visited", grade=4)
        with pytest.raises(ValueError, match="visited"):
            await visits.update_visit(11, VisitUpdate(status="missed", grade=2))

    async def test_status_cannot_be_nulled(self, visits):
        visits._repo.get_visit.return_value = _visit()
        with pytest.raises(ValueError, match="status"):
            await visits.update_visit(11, VisitUpdate.model_validate({"status": None}))

    async def test_unknown_visit(self, visits):
        visits._repo.get_visit.return_value = None
        assert await visits.update_visit(11, VisitUpdate(notes="x")) is None
        assert await visits.delete_visit(11) is False


@pytest.fixture
def places():
    svc = PlaceService(AsyncMock())
    svc._repo = AsyncMock()
    svc._tag_repo = AsyncMock()
    svc._visit_repo = AsyncMock()
    svc._stay_repo = AsyncMock()
    return svc


class TestPlaceService:
    async def test_list_attaches_the_derived_grade(self, places):
        places._repo.get_places.return_value = [_place(id=3), _place(id=4)]
        places._repo.get_grades.return_value = {3: (4.5, 2)}
        reads = await places.get_places(PlaceFilters())
        assert (reads[0].grade, reads[0].grade_count) == (4.5, 2)
        assert (reads[1].grade, reads[1].grade_count) == (None, 0)
        assert reads[0].tags == ["Would return"]

    async def test_create_resolves_tags(self, places):
        places._tag_repo.get_or_create_tags.return_value = [TravelTag(name="Family")]
        places._repo.create_place.return_value = _place()
        places._repo.get_grades.return_value = {}
        await places.create_place(PlaceCreate(kind="cafe", name="X", tags=["Family"]))
        fields, tags = places._repo.create_place.await_args.args
        assert "tags" not in fields and tags[0].name == "Family"

    async def test_update_without_tags_leaves_them_alone(self, places):
        places._repo.update_place.return_value = _place()
        places._repo.get_grades.return_value = {}
        await places.update_place(3, PlaceUpdate(notes="n"))
        assert places._repo.update_place.await_args.args[2] is None
        places._tag_repo.get_or_create_tags.assert_not_awaited()

    async def test_detail_includes_visits_and_stays(self, places):
        places._repo.get_place.return_value = _place()
        places._repo.get_grades.return_value = {3: (3.0, 1)}
        places._visit_repo.get_place_visits.return_value = [_visit(status="visited", grade=3)]
        places._stay_repo.get_place_stays.return_value = []
        detail = await places.get_place_detail(3)
        assert detail.grade == 3.0 and len(detail.visits) == 1 and detail.stays == []

    async def test_detail_unknown(self, places):
        places._repo.get_place.return_value = None
        assert await places.get_place_detail(3) is None


class TestTripItineraryHiding:
    @pytest.fixture
    def trips(self):
        svc = TripService(AsyncMock())
        for name in ("_repo", "_tag_repo", "_leg_repo", "_stay_repo", "_visit_repo", "settings_service"):
            setattr(svc, name, AsyncMock())
        svc.settings_service.get.return_value = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=60)
        svc._leg_repo.get_legs.return_value = []
        svc._stay_repo.get_stays.return_value = []
        svc._visit_repo.get_trip_visits.return_value = [
            _visit(id=1, status="visited"), _visit(id=2, status="planned"), _visit(id=3, status="missed"),
        ]
        return svc

    def _trip(self, end):
        return SimpleNamespace(
            id=1, name="T", start_date=date(2026, 5, 1), end_date=end, travelers=None, preferences=None,
            checklist_note_id=None, notes=None, default_tag_names=None, tags=[], created_at=NOW, updated_at=NOW,
        )

    @freeze_time("2026-06-10 12:00:00")
    async def test_ended_trip_hides_planned_and_missed(self, trips):
        trips._repo.get_trip.return_value = self._trip(date(2026, 6, 1))
        detail = await trips.get_trip_detail(1)
        assert [v.id for v in detail.visits] == [1] and detail.hidden_visit_count == 2

    @freeze_time("2026-06-10 12:00:00")
    async def test_ended_trip_shows_everything_on_request(self, trips):
        trips._repo.get_trip.return_value = self._trip(date(2026, 6, 1))
        detail = await trips.get_trip_detail(1, include_all_visits=True)
        assert len(detail.visits) == 3 and detail.hidden_visit_count == 0

    @freeze_time("2026-06-10 12:00:00")
    async def test_trip_still_running_keeps_its_itinerary(self, trips):
        trips._repo.get_trip.return_value = self._trip(date(2026, 6, 20))
        detail = await trips.get_trip_detail(1)
        assert len(detail.visits) == 3 and detail.hidden_visit_count == 0
