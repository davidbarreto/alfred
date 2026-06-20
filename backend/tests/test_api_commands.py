import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.assistant.intents.intent_service import IntentResult

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture(scope="module")
def client():
    from app.main import app
    from app.db.session import get_session
    from app.dependencies import get_llm_provider, get_extraction_llm_provider
    from app.shared.llm import LlmResponse

    mock_session = AsyncMock()
    mock_llm = AsyncMock()
    mock_llm.provider = "mock"
    mock_llm.model = "mock-model"
    mock_llm.complete = AsyncMock(return_value=LlmResponse(text="{}", tokens_input=0, tokens_output=0))

    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm
    app.dependency_overrides[get_extraction_llm_provider] = lambda: mock_llm
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDetectCommandIntent:
    def test_returns_intent_confidence_command_type_and_detected_intents(self, client):
        result = IntentResult(intent="task.list", confidence=0.91)
        with patch("app.api.routes.commands.detect_intent", new=AsyncMock(return_value=result)):
            response = client.post("/commands/intents", json={"text": "what are my tasks?"}, headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "task.list"
        assert data["confidence"] == 0.91
        assert data["command_type"] == "read"
        assert data["detected_intents"] == ["task.list"]

    def test_write_intent_returns_write_type_and_detected_intents(self, client):
        result = IntentResult(intent="task.add", confidence=0.88)
        with patch("app.api.routes.commands.detect_intent", new=AsyncMock(return_value=result)):
            response = client.post("/commands/intents", json={"text": "add a task"}, headers=AUTH)
        data = response.json()
        assert data["command_type"] == "write"
        assert data["detected_intents"] == ["task.add"]

    def test_unknown_intent_has_null_command_type_and_null_detected_intents(self, client):
        result = IntentResult(intent="unknown", confidence=0.2)
        with patch("app.api.routes.commands.detect_intent", new=AsyncMock(return_value=result)):
            response = client.post("/commands/intents", json={"text": "tell me a joke"}, headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "unknown"
        assert data["command_type"] is None
        assert data["detected_intents"] is None

    def test_low_confidence_returns_unknown(self, client):
        result = IntentResult(intent="task.add", confidence=0.3)
        with patch("app.api.routes.commands.detect_intent", new=AsyncMock(return_value=result)):
            response = client.post("/commands/intents", json={"text": "maybe add something"}, headers=AUTH)
        data = response.json()
        assert data["intent"] == "unknown"
        assert data["confidence"] == 0.3
        assert data["command_type"] is None
        assert data["detected_intents"] is None

    def test_requires_auth(self, client):
        response = client.post("/commands/intents", json={"text": "test"})
        assert response.status_code == 403

    def test_missing_text_returns_422(self, client):
        response = client.post("/commands/intents", json={}, headers=AUTH)
        assert response.status_code == 422


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

    def test_natural_language_returns_unknown_source(self, client):
        intent_result = IntentResult(intent="unknown", confidence=0.3)
        with patch(
            "app.assistant.commands.resolver.detect_intent",
            new=AsyncMock(return_value=intent_result),
        ):
            response = client.post(
                "/commands/resolve",
                json={"text": "This is not a command"},
                headers=AUTH,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["commands"][0]["source"] == "unknown"
        assert data["commands"][0]["args"] == {}

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
        assert cmd["args"]["priority"] == "HIGH"

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
        assert data["commands"][0]["args"]["title"] == "buy chocolate"

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
        assert data["commands"][0]["args"]["priority"] == "HIGH"

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

    def test_deterministic_source_field(self, client):
        response = client.post(
            "/commands/resolve",
            json={"text": "/taskadd Buy milk"},
            headers=AUTH,
        )
        assert response.json()["commands"][0]["source"] == "deterministic"

    def test_intent_detection_above_threshold(self, client):
        intent_result = IntentResult(intent="note.add", confidence=0.88)
        extracted = {"title": None, "content": "banana bread recipe"}
        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)), \
             patch("app.assistant.commands.resolver.extract_args", new=AsyncMock(return_value=extracted)):
            response = client.post(
                "/commands/resolve",
                json={"text": "Jot down banana bread recipe"},
                headers=AUTH,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        cmd = data["commands"][0]
        assert cmd["source"] == "intent_detection"
        assert cmd["type"] == "note"
        assert cmd["command"] == "add"
        assert cmd["confidence"] == 0.88
        assert cmd["args"] == extracted
