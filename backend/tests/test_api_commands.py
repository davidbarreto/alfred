import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


class TestResolveCommand:
    def test_task_add_command_resolves(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd Buy milk"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["commands"]) == 1
        assert data["commands"][0]["command"] == "add"
        assert data["commands"][0]["type"] == "task"

    def test_not_parsed_returns_ok_with_not_parsed_status(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "This is not a command"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_parsed"
        assert data["commands"] == []

    def test_raw_text_preserved_in_response(self, client):
        text = "/taskadd Finish report"
        response = client.post("/commands/resolve", json={"text": text}, headers=AUTH)
        assert response.json()["raw_text"] == text

    def test_multiple_commands(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd Buy milk /tasklist"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["commands"]) == 2

    def test_task_list_command(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/tasklist -p high"},
            headers=AUTH,
        )
        assert response.status_code == 200
        cmd = response.json()["commands"][0]
        assert cmd["command"] == "list"
        assert cmd["arguments"]["priority"] == "HIGH"

    def test_empty_text(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": ""},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "not_parsed"

    def test_requires_auth(self, client):
        response = client.post("/commands/resolve", json={"text": "/taskadd Test"})
        assert response.status_code == 403

    def test_wrong_token_rejected(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd Test"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert response.status_code == 401

    def test_missing_text_field(self, client):
        response = client.post("/commands/resolve", json={}, headers=AUTH)
        assert response.status_code == 422

    def test_command_hint_resolves_single_command(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd buy chocolate /noteadd chocolate is good", "command": "/taskadd", "args": "buy chocolate"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["commands"]) == 1
        assert data["commands"][0]["type"] == "task"
        assert data["commands"][0]["arguments"]["task"] == "buy chocolate"

    def test_command_hint_note_add(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/noteadd chocolate is good", "command": "/noteadd", "args": "chocolate is good"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["commands"][0]["type"] == "note"

    def test_command_hint_with_flags(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd buy milk -p high", "command": "/taskadd", "args": "buy milk -p high"},
            headers=AUTH,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["commands"][0]["arguments"]["priority"] == "HIGH"

    def test_command_hint_null_args_list_command(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/tasklist", "command": "/tasklist", "args": None},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["commands"][0]["command"] == "list"

    def test_command_hint_unknown_command_not_parsed(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/unknown", "command": "/unknown", "args": "something"},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "not_parsed"
