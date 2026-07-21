from datetime import datetime
from unittest.mock import AsyncMock

from app.integrations.google_calendar.provider import GoogleCalendarProvider


def _make_provider() -> GoogleCalendarProvider:
    return GoogleCalendarProvider(AsyncMock(), calendar_id="primary", entity_type="calendar_event")


class TestToGoogleEvent:
    def test_uses_record_timezone_when_set(self):
        provider = _make_provider()
        event = provider._to_google_event({
            "start_datetime": datetime(2026, 3, 15, 9, 0),
            "end_datetime": datetime(2026, 3, 15, 9, 30),
            "all_day": False,
            "timezone": "America/Chicago",
        })

        assert event["start"] == {"dateTime": "2026-03-15T09:00:00", "timeZone": "America/Chicago"}
        assert event["end"] == {"dateTime": "2026-03-15T09:30:00", "timeZone": "America/Chicago"}

    def test_falls_back_to_local_timezone_when_unset(self, monkeypatch):
        monkeypatch.setattr(
            "app.integrations.google_calendar.provider.local_timezone_name", lambda: "Europe/Lisbon"
        )
        provider = _make_provider()
        event = provider._to_google_event({
            "start_datetime": datetime(2026, 3, 15, 9, 0),
            "end_datetime": datetime(2026, 3, 15, 9, 30),
            "all_day": False,
        })

        assert event["start"]["timeZone"] == "Europe/Lisbon"
        assert event["end"]["timeZone"] == "Europe/Lisbon"

    def test_all_day_event_has_no_timezone(self):
        provider = _make_provider()
        event = provider._to_google_event({
            "start_datetime": datetime(2026, 3, 15, 0, 0),
            "end_datetime": datetime(2026, 3, 15, 23, 59, 59),
            "all_day": True,
            "timezone": "America/Chicago",
        })

        assert event["start"] == {"date": "2026-03-15"}
        assert event["end"] == {"date": "2026-03-15"}


class TestFromGoogleEvent:
    def test_converts_event_timezone_to_local(self):
        provider = _make_provider()
        record = provider._from_google_event({
            "id": "gc-1",
            "summary": "Standup",
            "start": {"dateTime": "2026-03-15T09:00:00-05:00", "timeZone": "America/Chicago"},
            "end": {"dateTime": "2026-03-15T09:30:00-05:00", "timeZone": "America/Chicago"},
        })

        # Chicago is UTC-5 (CDT) and Lisbon is UTC+0 (WET) on this date, a 5-hour gap.
        assert record["timezone"] == "America/Chicago"
        assert record["start_datetime"] == datetime(2026, 3, 15, 14, 0)
        assert record["end_datetime"] == datetime(2026, 3, 15, 14, 30)
        assert record["start_datetime"].tzinfo is None

    def test_falls_back_to_local_timezone_when_missing(self, monkeypatch):
        monkeypatch.setattr(
            "app.integrations.google_calendar.provider.local_timezone_name", lambda: "Europe/Lisbon"
        )
        provider = _make_provider()
        record = provider._from_google_event({
            "id": "gc-1",
            "summary": "Standup",
            "start": {"dateTime": "2026-03-15T09:00:00+00:00"},
            "end": {"dateTime": "2026-03-15T09:30:00+00:00"},
        })

        assert record["timezone"] == "Europe/Lisbon"
        assert record["start_datetime"] == datetime(2026, 3, 15, 9, 0)
        assert record["end_datetime"] == datetime(2026, 3, 15, 9, 30)

    def test_all_day_event_has_no_timezone(self):
        provider = _make_provider()
        record = provider._from_google_event({
            "id": "gc-1",
            "summary": "Holiday",
            "start": {"date": "2026-03-15"},
            "end": {"date": "2026-03-16"},
        })

        assert record["all_day"] is True
        assert record["timezone"] is None
