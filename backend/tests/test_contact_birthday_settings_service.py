import json

import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock

from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdayCascadeUpdate
from app.features.organizer.contacts.notification_settings.service import (
    CASCADES_KEY,
    DEFAULT_CASCADES,
    ContactBirthdaySettingsService,
)


@pytest.fixture
def stored():
    return {}


@pytest.fixture
def service(stored):
    svc = ContactBirthdaySettingsService.__new__(ContactBirthdaySettingsService)
    svc._settings = AsyncMock()
    svc._settings.get_value.side_effect = lambda key: stored.get(key)
    return svc


class TestGet:
    async def test_returns_defaults_when_unset(self, service):
        result = await service.get()
        assert result.relationships == DEFAULT_CASCADES

    async def test_merges_stored_overrides_over_defaults(self, service, stored):
        stored[CASCADES_KEY] = json.dumps({"friend": ["3d"]})
        result = await service.get()
        assert result.relationships["friend"] == ["3d"]
        assert result.relationships["family"] == DEFAULT_CASCADES["family"]

    async def test_ignores_unknown_stored_relationship(self, service, stored):
        stored[CASCADES_KEY] = json.dumps({"freind": ["3d"]})
        result = await service.get()
        assert result.relationships == DEFAULT_CASCADES


class TestLookAheads:
    async def test_default_to_the_old_constants(self, service):
        result = await service.get()
        assert (result.birthday_lookahead_days, result.birthday_dashboard_days) == (7, 30)

    async def test_stored_values_win(self, service, stored):
        stored["organizer.birthday_lookahead_days"] = "14"
        assert (await service.get()).birthday_lookahead_days == 14

    async def test_update_stores_only_the_given_fields(self, service):
        from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdaySettingsUpdate

        await service.update(ContactBirthdaySettingsUpdate(birthday_dashboard_days=60))
        service._settings.set_value.assert_awaited_once_with("organizer.birthday_dashboard_days", "60")


class TestGetCascade:
    async def test_returns_relationship_cascade(self, service):
        result = await service.get_cascade("family")
        assert result == DEFAULT_CASCADES["family"]

    async def test_none_relationship_falls_back_to_other(self, service):
        result = await service.get_cascade(None)
        assert result == DEFAULT_CASCADES["other"]

    async def test_unknown_relationship_falls_back_to_other(self, service):
        result = await service.get_cascade("bogus")
        assert result == DEFAULT_CASCADES["other"]


class TestUpdateRelationship:
    async def test_stores_merged_relationships_as_json(self, service):
        await service.update_relationship("friend", ContactBirthdayCascadeUpdate(offsets=["3d"]))
        stored_key, stored_value = service._settings.set_value.call_args.args
        assert stored_key == CASCADES_KEY
        stored = json.loads(stored_value)
        assert stored["friend"] == ["3d"]
        assert stored["family"] == DEFAULT_CASCADES["family"]

    def test_schema_rejects_invalid_offset(self):
        with pytest.raises(ValidationError, match="nonsense"):
            ContactBirthdayCascadeUpdate(offsets=["nonsense"])
