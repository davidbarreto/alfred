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

        assert result == FinanceSettingsRead(cycle_start_day=1)
        # The import matching constants the import used before they became settings.
        assert (result.import_knn_limit, result.import_knn_threshold, result.import_knn_min_vote) == (7, 0.72, 0.7)

    async def test_returns_stored_value(self, service):
        service._settings.get_value.side_effect = lambda key: "25" if key == CYCLE_START_DAY_KEY else None

        result = await service.get()

        assert result == FinanceSettingsRead(cycle_start_day=25)


    async def test_blank_row_falls_back_to_default(self, service):
        service._settings.get_value.return_value = ""

        result = await service.get()

        assert result == FinanceSettingsRead(cycle_start_day=1)


class TestGetCycleStartDay:
    async def test_returns_int(self, service):
        service._settings.get_value.side_effect = lambda key: "25" if key == CYCLE_START_DAY_KEY else None

        value = await service.get_cycle_start_day()

        assert value == 25


class TestUpdate:
    async def test_stores_as_string_and_returns_read_model(self, service):
        service._settings.get_value.side_effect = lambda key: "25" if key == CYCLE_START_DAY_KEY else None
        result = await service.update(FinanceSettingsUpdate(cycle_start_day=25))

        service._settings.set_value.assert_called_once_with(CYCLE_START_DAY_KEY, "25")
        assert result == FinanceSettingsRead(cycle_start_day=25)

    async def test_import_threshold_keeps_its_decimals(self, service):
        service._settings.get_value.side_effect = lambda key: "0.8" if key == "finance.import_knn_threshold" else None
        assert (await service.get()).import_knn_threshold == 0.8
