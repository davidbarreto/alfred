from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.contacts.schemas import ContactRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _contact_read(**kwargs):
    defaults = dict(id=1, provider_id="people/c1", name="Alice", email="alice@example.com", phone=None, birthday=None, is_self=False)
    defaults.update(kwargs)
    return ContactRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_contacts.return_value = [_contact_read()]
    svc.get_contact.return_value = _contact_read()
    svc.create_contact.return_value = _contact_read(id=2, provider_id="people/c2", name="Bob")
    svc.update_contact.return_value = _contact_read(name="Alice Updated")
    svc.delete_contact.return_value = None
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_contacts_crud_service
    app.dependency_overrides[get_contacts_crud_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetContacts:
    def test_returns_list(self, client):
        response = client.get("/organizer/contacts/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "Alice"

    def test_requires_auth(self, client):
        response = client.get("/organizer/contacts/")
        assert response.status_code == 403

    def test_wrong_token_rejected(self, client):
        response = client.get("/organizer/contacts/", headers={"Authorization": "Bearer bad-token"})
        assert response.status_code == 401

    def test_name_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/contacts/?name=alice", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.name == "alice"

    def test_email_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/contacts/?email=example.com", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.email == "example.com"

    def test_has_birthday_filter_true(self, client, mock_service):
        client.get("/organizer/contacts/?has_birthday=true", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.has_birthday is True

    def test_has_birthday_filter_false(self, client, mock_service):
        client.get("/organizer/contacts/?has_birthday=false", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.has_birthday is False

    def test_limit_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/contacts/?limit=25", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.limit == 25

    def test_letter_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/contacts/?letter=A", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.letter == "A"

    def test_letter_filter_uppercased(self, client, mock_service):
        client.get("/organizer/contacts/?letter=a", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.letter == "A"

    def test_offset_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/contacts/?offset=50", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.offset == 50

    def test_default_filters(self, client, mock_service):
        client.get("/organizer/contacts/", headers=AUTH)
        filters = mock_service.get_contacts.call_args[0][0]
        assert filters.limit == 100
        assert filters.offset == 0
        assert filters.name is None
        assert filters.email is None
        assert filters.letter is None
        assert filters.has_birthday is None


class TestGetContact:
    def test_found_returns_200(self, client):
        response = client.get("/organizer/contacts/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get_contact.return_value = None
        response = client.get("/organizer/contacts/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Contact not found"


class TestCreateContact:
    def test_creates_and_returns_201(self, client):
        payload = {"name": "Bob", "email": "bob@example.com"}
        response = client.post("/organizer/contacts/", json=payload, headers=AUTH)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Bob"

    def test_missing_name_returns_422(self, client):
        response = client.post("/organizer/contacts/", json={"email": "x@example.com"}, headers=AUTH)
        assert response.status_code == 422


class TestUpdateContact:
    def test_updates_and_returns_200(self, client):
        response = client.patch("/organizer/contacts/1", json={"name": "Alice Updated"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Alice Updated"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update_contact.return_value = None
        response = client.patch("/organizer/contacts/999", json={"name": "X"}, headers=AUTH)
        assert response.status_code == 404

    def test_marks_as_self(self, client, mock_service):
        mock_service.update_contact.return_value = _contact_read(is_self=True)
        response = client.patch("/organizer/contacts/1", json={"is_self": True}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["is_self"] is True


class TestDeleteContact:
    def test_returns_204(self, client):
        response = client.delete("/organizer/contacts/1", headers=AUTH)
        assert response.status_code == 204

    def test_delete_missing_returns_204(self, client, mock_service):
        mock_service.delete_contact.return_value = None
        response = client.delete("/organizer/contacts/999", headers=AUTH)
        assert response.status_code == 204
