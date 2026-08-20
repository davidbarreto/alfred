import json

import pytest
from unittest.mock import AsyncMock

from app.features.organizer.contacts.notification_settings.schemas import ContactBirthdayCascadeUpdate
from app.features.organizer.contacts.notification_settings.service import (
    CASCADES_KEY,
    DEFAULT_CASCADES,
    ContactBirthdaySettingsService,
)


@pytest.fixture
def service():
    svc = ContactBirthdaySettingsService.__new__(ContactBirthdaySettingsService)
    svc._settings = AsyncMock()
    return svc


class TestGet:
    async def test_returns_defaults_when_unset(self, service):
        service._settings.get_value.return_value = None
        result = await service.get()
        service._settings.get_value.assert_called_once_with(CASCADES_KEY)
        assert result.relationships == DEFAULT_CASCADES

    async def test_merges_stored_overrides_over_defaults(self, service):
        service._settings.get_value.return_value = json.dumps({"friend": ["3d"]})
        result = await service.get()
        assert result.relationships["friend"] == ["3d"]
        assert result.relationships["family"] == DEFAULT_CASCADES["family"]


class TestGetCascade:
    async def test_returns_relationship_cascade(self, service):
        service._settings.get_value.return_value = None
        result = await service.get_cascade("family")
        assert result == DEFAULT_CASCADES["family"]

    async def test_none_relationship_falls_back_to_other(self, service):
        service._settings.get_value.return_value = None
        result = await service.get_cascade(None)
        assert result == DEFAULT_CASCADES["other"]

    async def test_unknown_relationship_falls_back_to_other(self, service):
        service._settings.get_value.return_value = None
        result = await service.get_cascade("bogus")
        assert result == DEFAULT_CASCADES["other"]


class TestUpdateRelationship:
    async def test_stores_merged_relationships_as_json(self, service):
        service._settings.get_value.return_value = None
        await service.update_relationship("friend", ContactBirthdayCascadeUpdate(offsets=["3d"]))
        stored_key, stored_value = service._settings.set_value.call_args.args
        assert stored_key == CASCADES_KEY
        stored = json.loads(stored_value)
        assert stored["friend"] == ["3d"]
        assert stored["family"] == DEFAULT_CASCADES["family"]

    async def test_rejects_invalid_offset(self, service):
        service._settings.get_value.return_value = None
        with pytest.raises(Exception):
            await service.update_relationship("friend", ContactBirthdayCascadeUpdate(offsets=["nonsense"]))
