from unittest.mock import AsyncMock

import pytest

from app.features.travel.settings_schemas import TravelSettingsUpdate
from app.features.travel.settings_service import TravelSettingsService


@pytest.fixture
def service():
    svc = TravelSettingsService(AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    return svc


class TestHomeAddress:
    @pytest.mark.asyncio
    async def test_is_stored_in_the_organizer_namespace(self, service):
        await service.update(TravelSettingsUpdate(home_address="  Rua Exemplo 1 "))
        service._settings.set_value.assert_awaited_once_with("organizer.home_address", "Rua Exemplo 1")

    @pytest.mark.asyncio
    async def test_other_fields_stay_in_the_travel_namespace(self, service):
        await service.update(TravelSettingsUpdate(home_to_airport_min=30))
        service._settings.set_value.assert_awaited_once_with("travel.home_to_airport_min", "30")

    @pytest.mark.asyncio
    async def test_read_back_from_the_organizer_key_and_empty_is_none(self, service):
        values = {"organizer.home_address": "Rua Exemplo 1"}
        service._settings.get_value.side_effect = lambda key: values.get(key)
        assert (await service.get()).home_address == "Rua Exemplo 1"
        values["organizer.home_address"] = ""
        assert (await service.get()).home_address is None
