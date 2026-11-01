from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.shopping.errors import (
    ShoppingItemAlreadyPendingError,
    ShoppingProductBlockedError,
    ShoppingProductNameTakenError,
)
from app.features.organizer.shopping_products.schemas import ShoppingProductRead

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _read(**kwargs):
    defaults = dict(
        id=1, name="Milk", category_id=1, default_unit="l", default_quantity=None,
        purchase_count=3, pending=False, created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(kwargs)
    return ShoppingProductRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.list.return_value = [_read()]
    svc.get.return_value = _read()
    svc.create.return_value = _read(id=2, name="Rice")
    svc.update.return_value = _read(default_unit="kg")
    svc.delete.return_value = True
    svc.merge.return_value = _read(id=2)
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_shopping_product_service
    app.dependency_overrides[get_shopping_product_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListAndGet:
    def test_list_returns_products_with_counts(self, client):
        response = client.get("/organizer/shopping-products", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["purchase_count"] == 3

    def test_requires_auth(self, client):
        assert client.get("/organizer/shopping-products").status_code == 403

    def test_get_404(self, client, mock_service):
        mock_service.get.return_value = None
        assert client.get("/organizer/shopping-products/9", headers=AUTH).status_code == 404


class TestWrite:
    def test_create_returns_201(self, client):
        response = client.post("/organizer/shopping-products", json={"name": "Rice", "default_unit": "kg"}, headers=AUTH)
        assert response.status_code == 201

    def test_create_name_clash_is_409(self, client, mock_service):
        mock_service.create.side_effect = ShoppingProductNameTakenError("Rice")
        response = client.post("/organizer/shopping-products", json={"name": "Rice"}, headers=AUTH)
        assert response.status_code == 409
        assert "Rice" in response.json()["detail"]

    def test_rename_clash_is_409(self, client, mock_service):
        mock_service.update.side_effect = ShoppingProductNameTakenError("Rice")
        response = client.patch("/organizer/shopping-products/1", json={"name": "Rice"}, headers=AUTH)
        assert response.status_code == 409

    def test_update_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/organizer/shopping-products/9", json={"default_unit": "kg"}, headers=AUTH).status_code == 404

    def test_delete_204(self, client):
        assert client.delete("/organizer/shopping-products/1", headers=AUTH).status_code == 204

    def test_delete_blocked_is_409(self, client, mock_service):
        mock_service.delete.side_effect = ShoppingProductBlockedError("'Milk' is on the shopping list")
        assert client.delete("/organizer/shopping-products/1", headers=AUTH).status_code == 409

    def test_delete_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/organizer/shopping-products/9", headers=AUTH).status_code == 404


class TestMerge:
    def test_merge_returns_target(self, client, mock_service):
        response = client.post("/organizer/shopping-products/1/merge", json={"into_id": 2}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 2
        mock_service.merge.assert_awaited_once_with(1, 2)

    def test_merge_blocked_is_409(self, client, mock_service):
        mock_service.merge.side_effect = ShoppingProductBlockedError("both pending")
        assert client.post("/organizer/shopping-products/1/merge", json={"into_id": 2}, headers=AUTH).status_code == 409

    def test_merge_404(self, client, mock_service):
        mock_service.merge.return_value = None
        assert client.post("/organizer/shopping-products/1/merge", json={"into_id": 2}, headers=AUTH).status_code == 404


class TestShoppingItemConflict:
    def test_adding_a_pending_product_is_409_with_the_existing_item(self):
        from app.main import app
        from app.dependencies import get_shopping_service

        svc = AsyncMock()
        svc.create_item.side_effect = ShoppingItemAlreadyPendingError("Milk", 42)
        app.dependency_overrides[get_shopping_service] = lambda: svc
        try:
            response = TestClient(app).post("/organizer/shopping", json={"name": "Milk"}, headers=AUTH)
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409
        assert "already on the shopping list" in response.json()["detail"]
        assert "42" in response.json()["detail"]
