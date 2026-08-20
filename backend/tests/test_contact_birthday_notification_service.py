from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.organizer.contacts.notifications.service import ContactBirthdayNotificationService

TODAY = date(2026, 8, 20)


def _make_contact(id=1, name="Mom", birthday=None, relationship="family"):
    contact = MagicMock()
    contact.id = id
    contact.name = name
    contact.birthday = birthday or date(2000, 8, 23)
    contact.relationship = relationship
    return contact


@pytest.fixture
def service():
    svc = ContactBirthdayNotificationService.__new__(ContactBirthdayNotificationService)
    svc._contact_repo = AsyncMock()
    svc._settings = AsyncMock()
    svc._working_memory_repo = AsyncMock()
    return svc


def _patch_today():
    return patch(
        "app.features.organizer.contacts.notifications.service.local_now",
        return_value=MagicMock(date=MagicMock(return_value=TODAY)),
    )


class TestBuildDueDigest:
    async def test_fires_when_threshold_date_matches_today(self, service):
        # Aug 20 + 3 days = next birthday Aug 23.
        contact = _make_contact(birthday=date(2000, 8, 23))
        service._contact_repo.get_all_with_birthday.return_value = [contact]
        service._settings.get_cascade.return_value = ["3d"]
        service._working_memory_repo.list.return_value = []

        with _patch_today():
            digest = await service.build_due_digest()

        assert digest.has_content is True
        assert "Mom" in digest.text
        service._working_memory_repo.upsert.assert_awaited_once()

    async def test_no_match_when_offset_not_reached(self, service):
        contact = _make_contact(birthday=date(2000, 8, 23))
        service._contact_repo.get_all_with_birthday.return_value = [contact]
        service._settings.get_cascade.return_value = ["1d"]
        service._working_memory_repo.list.return_value = []

        with _patch_today():
            digest = await service.build_due_digest()

        assert digest.has_content is False

    async def test_dedup_suppresses_repeat_same_day(self, service):
        contact = _make_contact(birthday=date(2000, 8, 23))
        service._contact_repo.get_all_with_birthday.return_value = [contact]
        service._settings.get_cascade.return_value = ["3d"]
        service._working_memory_repo.list.return_value = [MagicMock()]

        with _patch_today():
            digest = await service.build_due_digest()

        assert digest.has_content is False
        service._working_memory_repo.upsert.assert_not_called()

    async def test_one_month_offset_is_calendar_exact(self, service):
        # Next birthday Aug 23; "1mo" before that is Jul 23, not today (Aug 20).
        contact = _make_contact(birthday=date(2000, 8, 23))
        service._contact_repo.get_all_with_birthday.return_value = [contact]
        service._settings.get_cascade.return_value = ["1mo"]
        service._working_memory_repo.list.return_value = []

        with _patch_today():
            digest = await service.build_due_digest()

        assert digest.has_content is False

    async def test_missing_relationship_uses_settings_fallback(self, service):
        contact = _make_contact(birthday=date(2000, 8, 23), relationship=None)
        service._contact_repo.get_all_with_birthday.return_value = [contact]
        service._settings.get_cascade.return_value = ["3d"]
        service._working_memory_repo.list.return_value = []

        with _patch_today():
            await service.build_due_digest()

        service._settings.get_cascade.assert_awaited_once_with(None)
