from unittest.mock import AsyncMock

import pytest

from app.features.core.settings.service import SettingService
from app.features.core.settings.schemas import SettingRead


@pytest.fixture
def service():
    svc = SettingService.__new__(SettingService)
    svc._repo = AsyncMock()
    return svc


class TestGetValue:
    async def test_returns_value_when_set(self, service):
        setting = AsyncMock()
        setting.value = "25"
        service._repo.get.return_value = setting

        value = await service.get_value("finance.cycle_start_day")

        assert value == "25"

    async def test_returns_default_when_unset(self, service):
        service._repo.get.return_value = None

        value = await service.get_value("finance.cycle_start_day", default="1")

        assert value == "1"

    async def test_returns_none_when_unset_and_no_default(self, service):
        service._repo.get.return_value = None

        value = await service.get_value("finance.cycle_start_day")

        assert value is None


class TestSetValue:
    async def test_sets_and_returns_read_model(self, service):
        from app.features.core.settings.tables import Setting
        from datetime import datetime, timezone

        service._repo.set.return_value = Setting(
            key="finance.cycle_start_day", value="25", updated_at=datetime.now(timezone.utc)
        )

        result = await service.set_value("finance.cycle_start_day", "25")

        service._repo.set.assert_called_once_with("finance.cycle_start_day", "25")
        assert isinstance(result, SettingRead)
        assert result.value == "25"
