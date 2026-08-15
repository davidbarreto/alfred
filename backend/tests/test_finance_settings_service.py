from unittest.mock import AsyncMock

import pytest

from app.features.finance.settings.service import CYCLE_START_DAY_KEY, FinanceSettingsService
from app.features.finance.settings.schemas import FinanceSettingsRead, FinanceSettingsUpdate


@pytest.fixture
def service():
    svc = FinanceSettingsService.__new__(FinanceSettingsService)
    svc._settings = AsyncMock()
    return svc


class TestGet:
    async def test_defaults_to_one_when_unset(self, service):
        service._settings.get_value.return_value = None

        result = await service.get()

        service._settings.get_value.assert_called_once_with(CYCLE_START_DAY_KEY)
        assert result == FinanceSettingsRead(cycle_start_day=1)

    async def test_returns_stored_value(self, service):
        service._settings.get_value.return_value = "25"

        result = await service.get()

        assert result == FinanceSettingsRead(cycle_start_day=25)


class TestGetCycleStartDay:
    async def test_returns_int(self, service):
        service._settings.get_value.return_value = "25"

        value = await service.get_cycle_start_day()

        assert value == 25


class TestUpdate:
    async def test_stores_as_string_and_returns_read_model(self, service):
        result = await service.update(FinanceSettingsUpdate(cycle_start_day=25))

        service._settings.set_value.assert_called_once_with(CYCLE_START_DAY_KEY, "25")
        assert result == FinanceSettingsRead(cycle_start_day=25)
