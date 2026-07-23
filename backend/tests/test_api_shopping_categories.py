import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.organizer.shopping_categories.schemas import ShoppingCategoryRead
from app.features.organizer.shopping_categories.service import ShoppingCategoryDeletionBlockedError

AUTH = {"Authorization": "Bearer test-api-token"}


def _category_read(**kwargs):
    defaults = dict(id=1, name="grocery")
    defaults.update(kwargs)
    return ShoppingCategoryRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _category_read()
    svc.list.return_value = [_category_read()]
    svc.create.return_value = _category_read(id=2, name="frozen")
    svc.update.return_value = _category_read(name="produce")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_shopping_category_service
    app.dependency_overrides[get_shopping_category_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListShoppingCategories:
    def test_returns_list(self, client):
        response = client.get("/organizer/shopping-categories/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "grocery"

    def test_requires_auth(self, client):
        assert client.get("/organizer/shopping-categories/").status_code == 403


class TestGetShoppingCategory:
    def test_found_returns_200(self, client):
        response = client.get("/organizer/shopping-categories/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/organizer/shopping-categories/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Shopping category not found"

    def test_requires_auth(self, client):
        assert client.get("/organizer/shopping-categories/1").status_code == 403


class TestCreateShoppingCategory:
    def test_creates_and_returns_201(self, client):
        response = client.post("/organizer/shopping-categories/", json={"name": "frozen"}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["name"] == "frozen"

    def test_missing_name_returns_422(self, client):
        assert client.post("/organizer/shopping-categories/", json={}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/organizer/shopping-categories/", json={"name": "X"}).status_code == 403


class TestUpdateShoppingCategory:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/organizer/shopping-categories/1", json={"name": "produce"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "produce"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/organizer/shopping-categories/999", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/organizer/shopping-categories/1", json={"name": "X"}).status_code == 403


class TestDeleteShoppingCategory:
    def test_deletes_returns_204(self, client):
        assert client.delete("/organizer/shopping-categories/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/organizer/shopping-categories/999", headers=AUTH).status_code == 404

    def test_blocked_returns_409(self, client, mock_service):
        mock_service.delete.side_effect = ShoppingCategoryDeletionBlockedError(1, 2, 1, 0)
        response = client.delete("/organizer/shopping-categories/1", headers=AUTH)
        assert response.status_code == 409
        assert "2 shopping item" in response.json()["detail"]

    def test_requires_auth(self, client):
        assert client.delete("/organizer/shopping-categories/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/organizer/shopping-categories/5", headers=AUTH)
        mock_service.delete.assert_called_once_with(5)
