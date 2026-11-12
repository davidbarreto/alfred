from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.briefing.morning_formatter_service import _build_context as morning_context
from app.features.briefing.evening_formatter_service import _build_context as evening_context
from app.features.briefing.schemas import EveningDigest, MorningBriefing, TripBrief, TripMarkBrief
from app.features.travel.briefing import TripBriefService, build_agenda, build_trip_brief
from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.timeline import TimelineItem
from app.features.travel.trips.today import TripToday
from app.features.travel.visits.schemas import VisitPlace, VisitRead

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY = date(2026, 12, 18)


def _item(kind, hour, title):
    at = datetime(2026, 12, 18, hour, tzinfo=timezone.utc)
    return TimelineItem(kind=kind, at=at, local=at.replace(tzinfo=None), timezone="UTC", title=title, ref_id=1)


def _visit(id, at, status="planned", day=DAY):
    place = VisitPlace(id=id, kind="museum", name=f"Museum {id}", city="Beta", maps_url=None, lat=None, lng=None)
    return VisitRead(id=id, place_id=id, place=place, trip_id=1, trip_name="T", status=status, visit_date=day,
                     visit_time=at, notes=None, grade=None, created_at=NOW, updated_at=NOW)


def _trip(timeline=(), visits=(), leave=None):
    return TripDetail(
        id=1, name="Example trip", start_date=date(2026, 12, 17), end_date=date(2026, 12, 24), travelers=None,
        preferences=None, checklist_note_id=None, notes=None, default_tag_names=None, tags=[], created_at=NOW,
        updated_at=NOW, legs=[], stays=[], timeline=list(timeline), warnings=[], visits=list(visits), leave_home_at=leave,
    )


class TestAgenda:
    def test_todays_steps_and_visits_in_time_order_with_untimed_last(self):
        trip = _trip(
            timeline=[_item("check_out", 10, "Check out: Hotel"), _item("arrival", 12, "Arrive: Beta"), _item("leg", 8, "A → B")],
            visits=[_visit(1, time(14, 30)), _visit(2, None), _visit(3, time(9), status="missed"), _visit(4, time(9), day=date(2026, 12, 19))],
        )
        assert build_agenda(trip, DAY) == ["08:00 A → B", "10:00 Check out: Hotel", "14:30 Visit: Museum 1", "Visit: Museum 2"]

    def test_empty_day(self):
        assert build_agenda(_trip(), DAY) == []


class TestBrief:
    def _view(self, to_mark=0):
        return TripToday(trip_id=1, trip_name="Example trip", date=DAY, timezone="UTC", to_mark=to_mark)

    def test_day_number_spend_and_leave_time_only_on_the_day_it_applies(self):
        leave = datetime(2026, 12, 18, 6, tzinfo=timezone.utc)
        brief = build_trip_brief(_trip(leave=leave), self._view(), Decimal("120.50"))
        assert (brief.day, brief.days, brief.spend_eur, brief.leave_home_at) == (2, 8, Decimal("120.50"), leave)
        other_day = build_trip_brief(_trip(leave=datetime(2026, 12, 17, 6, tzinfo=timezone.utc)), self._view(), None)
        assert other_day.leave_home_at is None


@pytest.fixture
def service():
    svc = TripBriefService(AsyncMock())
    svc._trips, svc._repo, svc._links = AsyncMock(), AsyncMock(), AsyncMock()
    return svc


class TestService:
    async def test_no_ongoing_trip_means_no_block(self, service):
        service._repo.get_trips_overlapping.return_value = []
        assert await service.morning() is None and await service.evening() is None

    async def test_morning_block_includes_the_spend(self, service):
        service._repo.get_trips_overlapping.return_value = [SimpleNamespace(id=1)]
        service._trips.get_trip_detail.return_value = _trip()
        service._links.get_trip_costs.return_value = SimpleNamespace(total=SimpleNamespace(total_eur=Decimal("10.00")))
        brief = await service.morning()
        assert brief.trip_name == "Example trip" and brief.spend_eur == Decimal("10.00")

    async def test_evening_block_only_when_visits_are_left_to_mark(self, service):
        service._repo.get_trips_overlapping.return_value = [SimpleNamespace(id=1)]
        service._trips.get_trip_detail.return_value = _trip()
        assert await service.evening() is None  # nothing planned today


class TestContext:
    def test_morning_context_lists_the_trip_block(self):
        brief = TripBrief(trip_name="Example trip", day=2, days=8, agenda=["08:00 A → B"], spend_eur=Decimal("10.00"))
        context = morning_context(MorningBriefing(date=DAY, tasks=[], events=[], weather=None, holidays=[], birthdays=[], trip=brief))
        assert "On a trip: Example trip, day 2 of 8" in context and "08:00 A → B" in context and "10.00 EUR" in context

    def test_morning_context_without_a_trip_is_unchanged(self):
        context = morning_context(MorningBriefing(date=DAY, tasks=[], events=[], weather=None, holidays=[], birthdays=[]))
        assert "On a trip" not in context

    def test_evening_context_mentions_visits_to_mark(self):
        digest = EveningDigest(date=DAY, wins=[], tasks=[], tomorrow_events=[], notes=[],
                               trip=TripMarkBrief(trip_name="Example trip", to_mark=2))
        assert "2 visit(s) still to mark" in evening_context(digest)


class TestFailSoft:
    async def test_a_broken_trip_block_never_takes_the_briefing_down(self, monkeypatch):
        from app.features.briefing import evening_summary_service as evening, morning_summary_service as morning

        class Boom:
            def __init__(self, session): pass
            async def morning(self): raise RuntimeError("db")
            async def evening(self): raise RuntimeError("db")

        monkeypatch.setattr(morning, "TripBriefService", Boom)
        monkeypatch.setattr(evening, "TripBriefService", Boom)
        assert await morning.MorningBriefingSummaryService(AsyncMock(), None, None, None)._fetch_trip() is None
        assert await evening.EveningDigestSummaryService(AsyncMock())._fetch_trip() is None
