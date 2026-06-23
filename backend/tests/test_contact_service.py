from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.contacts.service import (
    ContactService,
    _has_useful_data,
    _next_birthday,
    _parse_birthday,
    _to_row,
)


class TestHasUsefulData:
    def test_returns_true_when_name_present(self):
        raw = {"names": [{"displayName": "Alice"}]}
        assert _has_useful_data(raw) is True

    def test_returns_false_when_no_names(self):
        assert _has_useful_data({}) is False
        assert _has_useful_data({"names": []}) is False


class TestToRow:
    def test_basic_contact(self):
        raw = {
            "resourceName": "people/c123",
            "names": [{"displayName": "Alice"}],
            "emailAddresses": [{"value": "alice@example.com"}],
            "phoneNumbers": [{"value": "+351900000000"}],
            "birthdays": [],
        }
        row = _to_row(raw)
        assert row["provider_id"] == "people/c123"
        assert row["name"] == "Alice"
        assert row["email"] == "alice@example.com"
        assert row["phone"] == "+351900000000"
        assert row["birthday"] is None

    def test_missing_optional_fields(self):
        raw = {
            "resourceName": "people/c456",
            "names": [{"displayName": "Bob"}],
        }
        row = _to_row(raw)
        assert row["email"] is None
        assert row["phone"] is None
        assert row["birthday"] is None

    def test_birthday_parsed(self):
        raw = {
            "resourceName": "people/c789",
            "names": [{"displayName": "Carol"}],
            "birthdays": [{"date": {"year": 1990, "month": 3, "day": 15}}],
        }
        row = _to_row(raw)
        assert row["birthday"] == date(1990, 3, 15)


class TestParseBirthday:
    def test_full_date(self):
        assert _parse_birthday({"year": 1990, "month": 6, "day": 23}) == date(1990, 6, 23)

    def test_no_year_uses_placeholder(self):
        result = _parse_birthday({"year": 0, "month": 6, "day": 23})
        assert result is not None
        assert result.month == 6
        assert result.day == 23
        assert result.year == 2000

    def test_missing_month_returns_none(self):
        assert _parse_birthday({"day": 23}) is None

    def test_none_input_returns_none(self):
        assert _parse_birthday(None) is None


class TestNextBirthday:
    def test_birthday_later_this_year(self):
        bd = date(1990, 12, 25)
        today = date(2026, 6, 23)
        result = _next_birthday(bd, today)
        assert result == date(2026, 12, 25)

    def test_birthday_already_past_this_year(self):
        bd = date(1990, 1, 1)
        today = date(2026, 6, 23)
        result = _next_birthday(bd, today)
        assert result == date(2027, 1, 1)

    def test_birthday_today(self):
        bd = date(1990, 6, 23)
        today = date(2026, 6, 23)
        result = _next_birthday(bd, today)
        assert result == today

    def test_feb29_non_leap_year_falls_back_to_mar1(self):
        bd = date(2000, 2, 29)
        today = date(2026, 6, 23)
        result = _next_birthday(bd, today)
        assert result == date(2027, 3, 1)


class TestContactService:
    @pytest.fixture
    def mock_client(self):
        return AsyncMock()

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_client, mock_session):
        return ContactService(client=mock_client, session=mock_session)

    @pytest.mark.asyncio
    async def test_sync_returns_count(self, service, mock_client):
        mock_client.list_connections.return_value = [
            {"resourceName": "people/c1", "names": [{"displayName": "Alice"}]},
            {"resourceName": "people/c2", "names": [{"displayName": "Bob"}]},
        ]
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.upsert = AsyncMock(return_value=2)
            count = await service.sync()

        assert count == 2

    @pytest.mark.asyncio
    async def test_sync_skips_contacts_without_names(self, service, mock_client):
        mock_client.list_connections.return_value = [
            {"resourceName": "people/c1", "names": [{"displayName": "Alice"}]},
            {"resourceName": "people/c2"},
        ]
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.upsert = AsyncMock(return_value=1)
            count = await service.sync()
            call_args = MockRepo.return_value.upsert.call_args[0][0]

        assert len(call_args) == 1
        assert call_args[0]["provider_id"] == "people/c1"
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_upcoming_birthdays_within_window(self, service):
        today = date(2026, 6, 23)
        contact = MagicMock()
        contact.name = "Alice"
        contact.birthday = date(1990, 6, 28)

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_all_with_birthday = AsyncMock(return_value=[contact])
            result = await service.get_upcoming_birthdays(today)

        assert len(result) == 1
        assert result[0]["name"] == "Alice"
        assert result[0]["days_until"] == 5

    @pytest.mark.asyncio
    async def test_get_upcoming_birthdays_excludes_outside_window(self, service):
        today = date(2026, 6, 23)
        contact = MagicMock()
        contact.name = "Bob"
        contact.birthday = date(1990, 7, 20)

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_all_with_birthday = AsyncMock(return_value=[contact])
            result = await service.get_upcoming_birthdays(today)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_upcoming_birthdays_sorted_by_days(self, service):
        today = date(2026, 6, 23)
        c1 = MagicMock()
        c1.name = "Alice"
        c1.birthday = date(1990, 7, 4)
        c2 = MagicMock()
        c2.name = "Bob"
        c2.birthday = date(1990, 6, 25)

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_all_with_birthday = AsyncMock(return_value=[c1, c2])
            result = await service.get_upcoming_birthdays(today)

        assert result[0]["name"] == "Bob"
        assert result[1]["name"] == "Alice"
