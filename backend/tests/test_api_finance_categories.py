import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.categories.schemas import CategoryRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _category_read(**kwargs):
    defaults = dict(id=1, name="Groceries", parent_id=None)
    defaults.update(kwargs)
    return CategoryRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _category_read()
    svc.list.return_value = [_category_read()]
    svc.create.return_value = _category_read(id=2, name="Transport")
    svc.update.return_value = _category_read(name="Food & Groceries")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_category_service
    app.dependency_overrides[get_category_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListCategories:
    def test_returns_list(self, client):
        response = client.get("/finance/categories/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Groceries"

    def test_requires_auth(self, client):
        assert client.get("/finance/categories/").status_code == 403


class TestGetCategory:
    def test_found_returns_200(self, client):
        response = client.get("/finance/categories/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/categories/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Category not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/categories/1").status_code == 403


class TestCreateCategory:
    def test_creates_and_returns_201(self, client):
        response = client.post("/finance/categories/", json={"name": "Transport"}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["name"] == "Transport"

    def test_with_parent_id(self, client):
        response = client.post("/finance/categories/", json={"name": "Bus", "parent_id": 1}, headers=AUTH)
        assert response.status_code == 201

    def test_missing_name_returns_422(self, client):
        assert client.post("/finance/categories/", json={}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/finance/categories/", json={"name": "X"}).status_code == 403


class TestUpdateCategory:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/categories/1", json={"name": "Food & Groceries"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Food & Groceries"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/finance/categories/999", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/categories/1", json={"name": "X"}).status_code == 403


class TestDeleteCategory:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/categories/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/categories/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/categories/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/finance/categories/5", headers=AUTH)
        mock_service.delete.assert_called_once_with(5)
