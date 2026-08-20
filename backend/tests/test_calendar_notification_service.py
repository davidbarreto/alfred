from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.organizer.calendar_events.notifications.service import CalendarNotificationService

NOW = datetime(2026, 8, 20, 10, 0)


def _make_event(id=1, title="Interview", start_datetime=None, all_day=False, notification_profile="light"):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime or NOW
    event.all_day = all_day
    event.notification_profile = notification_profile
    return event


@pytest.fixture
def service():
    svc = CalendarNotificationService.__new__(CalendarNotificationService)
    svc._event_service = AsyncMock()
    svc._settings = AsyncMock()
    svc._working_memory_repo = AsyncMock()
    return svc


def _patch_now():
    return patch("app.features.organizer.calendar_events.notifications.service.local_now", return_value=NOW)


class TestBuildDueDigest:
    async def test_fires_when_now_matches_offset_target(self, service):
        event = _make_event(start_datetime=NOW, notification_profile="light")
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["0"]
        service._working_memory_repo.list.return_value = []

        with _patch_now():
            digest = await service.build_due_digest()

        assert digest.has_content is True
        assert "Interview" in digest.text
        service._working_memory_repo.upsert.assert_awaited_once()

    async def test_no_match_when_offset_target_not_reached(self, service):
        from datetime import timedelta
        event = _make_event(start_datetime=NOW + timedelta(hours=2), notification_profile="light")
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["5m"]
        service._working_memory_repo.list.return_value = []

        with _patch_now():
            digest = await service.build_due_digest()

        assert digest.has_content is False

    async def test_dedup_suppresses_repeat(self, service):
        event = _make_event(start_datetime=NOW, notification_profile="light")
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["0"]
        service._working_memory_repo.list.return_value = [MagicMock()]

        with _patch_now():
            digest = await service.build_due_digest()

        assert digest.has_content is False
        service._working_memory_repo.upsert.assert_not_called()

    async def test_null_profile_falls_back_to_normal(self, service):
        event = _make_event(start_datetime=NOW, notification_profile=None)
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["0"]
        service._working_memory_repo.list.return_value = []

        with _patch_now():
            await service.build_due_digest()

        service._settings.get_cascade.assert_awaited_once_with("normal")

    async def test_all_day_event_skips_sub_day_offsets(self, service):
        event = _make_event(start_datetime=NOW, all_day=True, notification_profile="cant_miss")
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["1h", "30m"]
        service._working_memory_repo.list.return_value = []

        with _patch_now():
            digest = await service.build_due_digest()

        assert digest.has_content is False
        service._working_memory_repo.upsert.assert_not_called()

    async def test_all_day_event_allows_at_time_offset(self, service):
        event = _make_event(start_datetime=NOW, all_day=True, notification_profile="cant_miss")
        service._event_service.get_events.return_value = [event]
        service._settings.get_cascade.return_value = ["0"]
        service._working_memory_repo.list.return_value = []

        with _patch_now():
            digest = await service.build_due_digest()

        assert digest.has_content is True
