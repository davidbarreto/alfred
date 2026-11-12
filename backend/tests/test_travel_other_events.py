from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.travel.other_events import (
    TripSnoozeService, TripSpan, is_trip_event, snoozed_keys, span_of, trips_on,
)


def _event(id, day, tags=(), recurrence_rule=None, hour=9):
    start = datetime(2026, 12, day, hour)
    return SimpleNamespace(
        id=id, title=f"Event {id}", tags=list(tags), recurrence_rule=recurrence_rule, start_datetime=start,
        end_datetime=start.replace(hour=hour + 1), all_day=False,
    )


SPAN = TripSpan(date(2026, 12, 17), date(2026, 12, 29), frozenset({"travel"}))


class TestRules:
    def test_span_lowercases_the_default_tags_and_ignores_blanks(self):
        trip = SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 29), default_tag_names="Travel, ,Work")
        assert span_of(trip).tags == frozenset({"travel", "work"})

    def test_trips_on_is_inclusive(self):
        assert trips_on(date(2026, 12, 17), [SPAN]) and trips_on(date(2026, 12, 29), [SPAN])
        assert not trips_on(date(2026, 12, 30), [SPAN])

    def test_tag_match_is_case_insensitive(self):
        assert is_trip_event(_event(1, 18, tags=["TRAVEL"]), set(), [SPAN])

    def test_a_linked_event_is_a_trip_event_even_without_tags(self):
        assert is_trip_event(_event(1, 18), {1}, [SPAN])

    def test_an_untagged_unlinked_event_is_other(self):
        assert not is_trip_event(_event(1, 18), set(), [SPAN])

    def test_a_trip_without_default_tags_relies_on_links_alone(self):
        bare = TripSpan(SPAN.start, SPAN.end, frozenset())
        assert not is_trip_event(_event(1, 18, tags=["Travel"]), set(), [bare])


class TestSnoozedKeys:
    def test_only_other_events_on_trip_days_are_held(self):
        events = [_event(1, 18), _event(2, 18, tags=["travel"]), _event(3, 18), _event(4, 5)]
        assert snoozed_keys(events, {3}, [SPAN]) == {(1, datetime(2026, 12, 18, 9))}

    def test_a_recurring_event_is_held_per_occurrence_on_trip_days_only(self):
        events = [_event(1, 14, recurrence_rule="FREQ=WEEKLY"), _event(1, 21, recurrence_rule="FREQ=WEEKLY")]
        assert snoozed_keys(events, set(), [SPAN]) == {(1, datetime(2026, 12, 21, 9))}


@pytest.fixture
def service():
    svc = TripSnoozeService(AsyncMock(), AsyncMock())
    svc._events, svc._settings, svc._trips = AsyncMock(), AsyncMock(), AsyncMock()
    svc._legs, svc._stays, svc._visits = AsyncMock(), AsyncMock(), AsyncMock()
    for repo in (svc._legs, svc._stays, svc._visits):
        repo.get_imported_event_ids.return_value = {}
    svc._settings.get.return_value = SimpleNamespace(snooze_other_events=True)
    svc._trips.get_trips_overlapping.return_value = [
        SimpleNamespace(start_date=date(2026, 12, 17), end_date=date(2026, 12, 29), default_tag_names="Travel")
    ]
    return svc


class TestSnoozeService:
    async def test_holds_other_events_when_enabled(self, service):
        assert await service.snoozed_for_digest([_event(1, 18)]) == {(1, datetime(2026, 12, 18, 9))}

    async def test_does_nothing_when_the_setting_is_off(self, service):
        service._settings.get.return_value = SimpleNamespace(snooze_other_events=False)
        assert await service.snoozed_for_digest([_event(1, 18)]) == set()
        service._trips.get_trips_overlapping.assert_not_awaited()

    async def test_events_linked_to_a_visit_are_never_held(self, service):
        service._visits.get_imported_event_ids.return_value = {1: 11}
        assert await service.snoozed_for_digest([_event(1, 18)]) == set()

    async def test_fails_open_when_anything_breaks(self, service, caplog):
        service._trips.get_trips_overlapping.side_effect = RuntimeError("db down")
        assert await service.snoozed_for_digest([_event(1, 18)]) == set()
        assert "Trip snooze skipped" in caplog.text

    async def test_no_events_no_queries(self, service):
        assert await service.snoozed_for_digest([]) == set()
        service._settings.get.assert_not_awaited()


class TestOtherEventsList:
    async def test_lists_other_events_with_the_snooze_flag(self, service):
        service._trips.get_trip.return_value = SimpleNamespace(
            start_date=date(2099, 12, 17), end_date=date(2099, 12, 29), default_tag_names="Travel")
        mine, other = _event(1, 18, tags=["travel"]), _event(2, 18, recurrence_rule="FREQ=WEEKLY")
        for e in (mine, other):
            e.start_datetime = e.start_datetime.replace(year=2099)
            e.end_datetime = e.end_datetime.replace(year=2099)
        service._events.get_events.return_value = [mine, other]
        result = await service.get_other_events(1)
        assert [(o.event_id, o.recurring, o.snoozed) for o in result] == [(2, True, True)]

    async def test_unknown_trip(self, service):
        service._trips.get_trip.return_value = None
        assert await service.get_other_events(9) is None
