import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.finance.tags.schemas import TagRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _tag_read(**kwargs):
    defaults = dict(id=1, name="Travel")
    defaults.update(kwargs)
    return TagRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = _tag_read()
    svc.list.return_value = [_tag_read()]
    svc.create.return_value = _tag_read(id=2, name="Work")
    svc.update.return_value = _tag_read(name="Business")
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_tag_service
    app.dependency_overrides[get_tag_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListTags:
    def test_returns_list(self, client):
        response = client.get("/finance/tags/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["name"] == "Travel"

    def test_requires_auth(self, client):
        assert client.get("/finance/tags/").status_code == 403


class TestGetTag:
    def test_found_returns_200(self, client):
        response = client.get("/finance/tags/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get.return_value = None
        response = client.get("/finance/tags/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Tag not found"

    def test_requires_auth(self, client):
        assert client.get("/finance/tags/1").status_code == 403


class TestCreateTag:
    def test_creates_and_returns_201(self, client):
        response = client.post("/finance/tags/", json={"name": "Work"}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["name"] == "Work"

    def test_missing_name_returns_422(self, client):
        assert client.post("/finance/tags/", json={}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.post("/finance/tags/", json={"name": "X"}).status_code == 403


class TestUpdateTag:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/finance/tags/1", json={"name": "Business"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Business"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/finance/tags/999", json={"name": "X"}, headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.patch("/finance/tags/1", json={"name": "X"}).status_code == 403


class TestDeleteTag:
    def test_deletes_returns_204(self, client):
        assert client.delete("/finance/tags/1", headers=AUTH).status_code == 204

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/finance/tags/999", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.delete("/finance/tags/1").status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/finance/tags/5", headers=AUTH)
        mock_service.delete.assert_called_once_with(5)
