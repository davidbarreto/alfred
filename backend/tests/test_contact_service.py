from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.contacts.service import (
    ContactService,
    _has_useful_data,
    _next_birthday,
    _parse_birthday,
    _parse_birthday_text,
    _to_row,
)
from app.features.organizer.contacts.schemas import ContactCreate, ContactFilters, ContactRead, ContactUpdate


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

    def test_birthday_parsed_from_date(self):
        raw = {
            "resourceName": "people/c789",
            "names": [{"displayName": "Carol"}],
            "birthdays": [{"date": {"year": 1990, "month": 3, "day": 15}}],
        }
        row = _to_row(raw)
        assert row["birthday"] == date(1990, 3, 15)

    def test_birthday_parsed_from_text_fallback(self):
        raw = {
            "resourceName": "people/c999",
            "names": [{"displayName": "Dave"}],
            "birthdays": [{"text": "March 15"}],
        }
        row = _to_row(raw)
        assert row["birthday"] is not None
        assert row["birthday"].month == 3
        assert row["birthday"].day == 15


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

    def test_text_fallback_when_no_date(self):
        result = _parse_birthday(None, "June 23, 1990")
        assert result == date(1990, 6, 23)

    def test_text_fallback_no_year(self):
        result = _parse_birthday(None, "June 23")
        assert result is not None
        assert result.month == 6
        assert result.day == 23

    def test_date_takes_priority_over_text(self):
        result = _parse_birthday({"year": 1990, "month": 6, "day": 23}, "March 15")
        assert result == date(1990, 6, 23)

    def test_unparseable_text_returns_none(self):
        result = _parse_birthday(None, "sometime in summer")
        assert result is None


class TestParseBirthdayText:
    def test_long_month_with_year(self):
        assert _parse_birthday_text("June 15, 1990") == date(1990, 6, 15)

    def test_short_month_with_year(self):
        assert _parse_birthday_text("Jun 15, 1990") == date(1990, 6, 15)

    def test_iso_format(self):
        assert _parse_birthday_text("1990-06-15") == date(1990, 6, 15)

    def test_us_slash_format(self):
        assert _parse_birthday_text("06/15/1990") == date(1990, 6, 15)

    def test_long_month_no_year(self):
        result = _parse_birthday_text("June 15")
        assert result is not None
        assert result.month == 6
        assert result.day == 15

    def test_unrecognised_format_returns_none(self):
        assert _parse_birthday_text("not a date") is None


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


def _make_contact_orm(id=1, provider_id="people/c1", name="Alice", email="alice@example.com", phone=None, birthday=None, is_self=False):
    c = MagicMock()
    c.id = id
    c.provider_id = provider_id
    c.name = name
    c.email = email
    c.phone = phone
    c.birthday = birthday
    c.is_self = is_self
    c.model_fields = {}
    return c


class TestContactService:
    @pytest.fixture
    def mock_client(self):
        return AsyncMock()

    @pytest.fixture
    def mock_provider(self):
        return AsyncMock()

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_client, mock_session):
        return ContactService(session=mock_session, client=mock_client)

    @pytest.fixture
    def service_with_provider(self, mock_client, mock_provider, mock_session):
        return ContactService(session=mock_session, client=mock_client, provider=mock_provider)

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
    async def test_sync_raises_503_when_client_is_none(self, mock_session):
        from fastapi import HTTPException
        svc = ContactService(session=mock_session)
        with pytest.raises(HTTPException) as exc_info:
            await svc.sync()
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_get_upcoming_birthdays_within_window(self, service):
        today = date(2026, 6, 23)
        contact = MagicMock()
        contact.name = "Alice"
        contact.birthday = date(1990, 6, 28)
        contact.is_self = False

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
        contact.is_self = False

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_all_with_birthday = AsyncMock(return_value=[contact])
            result = await service.get_upcoming_birthdays(today)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_upcoming_birthdays_excludes_self(self, service):
        today = date(2026, 6, 23)
        contact = MagicMock()
        contact.name = "David Barreto"
        contact.birthday = date(1990, 6, 28)
        contact.is_self = True

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
        c1.is_self = False
        c2 = MagicMock()
        c2.name = "Bob"
        c2.birthday = date(1990, 6, 25)
        c2.is_self = False

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_all_with_birthday = AsyncMock(return_value=[c1, c2])
            result = await service.get_upcoming_birthdays(today)

        assert result[0]["name"] == "Bob"
        assert result[1]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_contact_returns_read(self, service):
        orm = _make_contact_orm()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=orm)
            result = await service.get_contact(1)
        assert isinstance(result, ContactRead)
        assert result.name == "Alice"

    @pytest.mark.asyncio
    async def test_get_contact_returns_none_when_missing(self, service):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=None)
            result = await service.get_contact(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_contacts_returns_list(self, service):
        orm = _make_contact_orm()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contacts = AsyncMock(return_value=[orm])
            filters = ContactFilters()
            result = await service.get_contacts(filters)
        assert len(result) == 1
        assert result[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_create_contact_raises_503_without_provider(self, service):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.create_contact(ContactCreate(name="New Person"))
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_create_contact_write_through(self, service_with_provider, mock_provider):
        mock_provider.create = AsyncMock(return_value={"id": "people/cnew"})
        orm = _make_contact_orm(id=5, provider_id="people/cnew", name="New Person")
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.create_contact = AsyncMock(return_value=orm)
            result = await service_with_provider.create_contact(ContactCreate(name="New Person"))

        mock_provider.create.assert_called_once()
        assert result.provider_id == "people/cnew"

    @pytest.mark.asyncio
    async def test_update_contact_returns_none_when_missing(self, service_with_provider):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=None)
            result = await service_with_provider.update_contact(999, ContactUpdate(name="X"))
        assert result is None

    @pytest.mark.asyncio
    async def test_update_contact_raises_503_without_provider(self, service):
        from fastapi import HTTPException
        orm = _make_contact_orm()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=orm)
            with pytest.raises(HTTPException) as exc_info:
                await service.update_contact(1, ContactUpdate(name="Updated"))
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_update_contact_write_through(self, service_with_provider, mock_provider):
        orm = _make_contact_orm()
        updated_orm = _make_contact_orm(name="Updated Alice")
        mock_provider.update = AsyncMock(return_value={"id": "people/c1"})
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=orm)
            MockRepo.return_value.update_contact = AsyncMock(return_value=updated_orm)
            result = await service_with_provider.update_contact(1, ContactUpdate(name="Updated Alice"))

        mock_provider.update.assert_called_once()
        assert result.name == "Updated Alice"

    @pytest.mark.asyncio
    async def test_delete_contact_raises_503_without_provider(self, service):
        from fastapi import HTTPException
        orm = _make_contact_orm()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=orm)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_contact(1)
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_delete_contact_noop_when_missing(self, service_with_provider):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=None)
            await service_with_provider.delete_contact(999)
            MockRepo.return_value.delete_contact.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_contact_write_through(self, service_with_provider, mock_provider):
        orm = _make_contact_orm()
        mock_provider.delete = AsyncMock()
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.features.organizer.contacts.service.ContactRepository"
        ) as MockRepo:
            MockRepo.return_value.get_contact = AsyncMock(return_value=orm)
            MockRepo.return_value.delete_contact = AsyncMock()
            await service_with_provider.delete_contact(1)

        mock_provider.delete.assert_called_once()
        assert mock_provider.delete.call_args[0][0] == "people/c1"
