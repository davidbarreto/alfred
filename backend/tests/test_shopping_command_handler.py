from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.shopping import handle_shopping
from app.features.organizer.shopping.errors import ShoppingItemAlreadyPendingError, ShoppingProductNameTakenError


@pytest.fixture
def service():
    svc = AsyncMock()
    svc.resolve_category_id.return_value = 1
    return svc


class TestAdd:
    async def test_already_pending_becomes_409_with_the_message(self, service):
        service.create_item.side_effect = ShoppingItemAlreadyPendingError("Milk", 42)

        with pytest.raises(HTTPException) as exc_info:
            await handle_shopping("shopping", "add", {"name": "Milk"}, service)

        assert exc_info.value.status_code == 409
        assert "already on the shopping list" in exc_info.value.detail

    async def test_passes_unit_through(self, service):
        service.create_item.return_value = MagicMock(model_dump=MagicMock(return_value={"id": 1}))

        await handle_shopping("shopping", "add", {"name": "Rice", "unit": "kg", "quantity": "2"}, service)

        data = service.create_item.call_args[0][0]
        assert (data.name, data.unit, str(data.quantity)) == ("Rice", "kg", "2")


class TestUpdate:
    async def test_unit_is_updatable(self, service):
        service.update_item.return_value = MagicMock(model_dump=MagicMock(return_value={"id": 1}))

        await handle_shopping("shopping", "update", {"id": "1", "unit": "kg"}, service)

        assert service.update_item.call_args[0][1].unit == "kg"

    async def test_rename_clash_becomes_409(self, service):
        service.update_item.side_effect = ShoppingProductNameTakenError("Rice")

        with pytest.raises(HTTPException) as exc_info:
            await handle_shopping("shopping", "update", {"id": "1", "name": "Rice"}, service)

        assert exc_info.value.status_code == 409
