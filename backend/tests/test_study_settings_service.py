from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.features.study.settings.schemas import StudySettingsUpdate
from app.features.study.settings.service import MAX_ACTIVE_PLANS_KEY, StudySettingsService


@pytest.fixture
def service():
    svc = StudySettingsService(session=AsyncMock())
    svc._settings = AsyncMock()
    return svc


class TestGet:
    async def test_defaults_to_three_when_unset(self, service):
        service._settings.get_value.return_value = None
        assert (await service.get()).max_active_plans == 3
        service._settings.get_value.assert_awaited_once_with(MAX_ACTIVE_PLANS_KEY)

    async def test_reads_stored_value(self, service):
        service._settings.get_value.return_value = "5"
        assert await service.get_max_active_plans() == 5


class TestUpdate:
    async def test_stores_value(self, service):
        result = await service.update(StudySettingsUpdate(max_active_plans=2))
        service._settings.set_value.assert_awaited_once_with(MAX_ACTIVE_PLANS_KEY, "2")
        assert result.max_active_plans == 2

    @pytest.mark.parametrize("value", [0, 11])
    def test_rejects_out_of_range(self, value):
        with pytest.raises(ValidationError):
            StudySettingsUpdate(max_active_plans=value)
