import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.api.routes.commands import (
    _cap_response_length,
    _format_result,
    _summarize_list,
    _LIST_DISPLAY_LIMIT,
    _MAX_RESPONSE_CHARS,
    _TEXT_FIELD_MAX,
)
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


class TestDetectCommand:
    def test_slash_command_returns_full_parse(self, client):
        response = client.post("/commands/detect", json={"text": "/taskadd Do the laundry"}, headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["operation_type"] == "write"
        assert len(data["commands"]) == 1
        cmd = data["commands"][0]
        assert cmd["type"] == "task"
        assert cmd["command"] == "add"
        assert cmd["source"] == "deterministic"
        assert cmd["confidence"] == 1.0
        assert cmd["args"]["title"] == "Do the laundry"

    def test_slash_command_in_middle_of_text(self, client):
        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock()) as mock_detect:
            response = client.post("/commands/detect", json={"text": "Hey /taskadd Buy milk"}, headers=AUTH)
        mock_detect.assert_not_called()
        data = response.json()
        assert data["operation_type"] == "write"
        assert data["commands"][0]["source"] == "deterministic"

    def test_multiple_slash_commands(self, client):
        response = client.post("/commands/detect", json={"text": "/taskadd Buy milk /tasklist"}, headers=AUTH)
        data = response.json()
        assert len(data["commands"]) == 2
        assert data["commands"][0]["command"] == "add"
        assert data["commands"][1]["command"] == "list"

    def test_read_command_returns_read_type(self, client):
        response = client.post("/commands/detect", json={"text": "/tl"}, headers=AUTH)
        data = response.json()
        assert data["operation_type"] == "read"
        assert data["commands"][0]["command"] == "list"

    def test_nl_intent_above_threshold_no_args(self, client):
        intent_result = IntentResult(intent="task.add", confidence=0.88)
        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)):
            response = client.post("/commands/detect", json={"text": "add a task buy groceries"}, headers=AUTH)
        data = response.json()
        assert data["operation_type"] == "write"
        assert data["commands"][0]["source"] == "intent_detection"
        assert data["commands"][0]["args"] == {}

    def test_nl_unknown_returns_no_commands(self, client):
        intent_result = IntentResult(intent="unknown", confidence=0.2)
        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)):
            response = client.post("/commands/detect", json={"text": "tell me a joke"}, headers=AUTH)
        data = response.json()
        assert data["operation_type"] is None
        assert data["commands"] == []

    def test_nl_below_threshold_returns_no_commands(self, client):
        intent_result = IntentResult(intent="task.add", confidence=0.3)
        with patch("app.assistant.commands.resolver.detect_intent", new=AsyncMock(return_value=intent_result)):
            response = client.post("/commands/detect", json={"text": "maybe add something"}, headers=AUTH)
        data = response.json()
        assert data["operation_type"] is None
        assert data["commands"] == []

    def test_command_hint_resolves_single_command(self, client):
        response = client.post(
            "/commands/detect",
            json={"text": "/taskadd buy chocolate /noteadd chocolate is good", "command": "/taskadd", "args": "buy chocolate"},
            headers=AUTH,
        )
        data = response.json()
        assert len(data["commands"]) == 1
        assert data["commands"][0]["type"] == "task"
        assert data["commands"][0]["args"]["title"] == "buy chocolate"

    def test_command_hint_with_flags(self, client):
        response = client.post(
            "/commands/detect",
            json={"text": "/taskadd buy milk -p high", "command": "/taskadd", "args": "buy milk -p high"},
            headers=AUTH,
        )
        assert response.json()["commands"][0]["args"]["priority"] == "HIGH"

    def test_command_hint_null_args_list_command(self, client):
        response = client.post(
            "/commands/detect",
            json={"text": "/tasklist", "command": "/tasklist", "args": None},
            headers=AUTH,
        )
        assert response.json()["commands"][0]["command"] == "list"

    def test_command_hint_unknown_command_returns_no_commands(self, client):
        response = client.post(
            "/commands/detect",
            json={"text": "/unknown", "command": "/unknown", "args": "something"},
            headers=AUTH,
        )
        assert response.json()["commands"] == []
        assert response.json()["operation_type"] is None

    def test_raw_text_preserved(self, client):
        text = "/taskadd Finish report"
        response = client.post("/commands/detect", json={"text": text}, headers=AUTH)
        assert response.json()["raw_text"] == text

    def test_requires_auth(self, client):
        response = client.post("/commands/detect", json={"text": "test"})
        assert response.status_code == 403

    def test_missing_text_returns_422(self, client):
        response = client.post("/commands/detect", json={}, headers=AUTH)
        assert response.status_code == 422


class TestExtractCommand:
    def test_extract_returns_args_for_known_intent(self, client):
        with patch(
            "app.api.routes.commands.extract_args",
            new=AsyncMock(return_value={"title": "Buy milk", "due_date": None, "priority": None}),
        ):
            response = client.post(
                "/commands/extract",
                json={"text": "I need to buy milk tomorrow", "intent": "task.add"},
                headers=AUTH,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["intent"] == "task.add"
        assert data["args"]["title"] == "Buy milk"

    def test_extract_unknown_intent_returns_empty_args(self, client):
        with patch("app.api.routes.commands.extract_args", new=AsyncMock(return_value={})):
            response = client.post(
                "/commands/extract",
                json={"text": "some text", "intent": "unknown.intent"},
                headers=AUTH,
            )
        data = response.json()
        assert data["args"] == {}

    def test_requires_auth(self, client):
        response = client.post("/commands/extract", json={"text": "test", "intent": "task.add"})
        assert response.status_code == 403

    def test_missing_fields_returns_422(self, client):
        response = client.post("/commands/extract", json={"text": "test"}, headers=AUTH)
        assert response.status_code == 422


class TestSummarizeList:
    def test_empty_list(self):
        assert _summarize_list([]) == "(empty — no items found)"

    def test_under_limit_no_truncation_note(self):
        items = [{"id": i, "title": f"Note {i}"} for i in range(3)]
        result = _summarize_list(items)
        assert result.startswith("3 item(s):")
        assert "not shown" not in result

    def test_over_limit_reports_total_and_omitted_ids(self):
        items = [{"id": i, "title": f"Note {i}"} for i in range(25)]
        result = _summarize_list(items)
        assert "25 item(s) total, showing 10 most recent" in result
        assert "15 more not shown" in result
        assert "IDs not shown:" in result
        for i in range(10, 25):
            assert str(i) in result

    def test_long_text_field_is_truncated(self):
        long_content = "x" * 1000
        items = [{"id": 1, "content": long_content}]
        result = _summarize_list(items)
        assert long_content not in result
        assert "x" * _TEXT_FIELD_MAX in result

    def test_non_dict_items_pass_through(self):
        result = _summarize_list([1, 2, 3])
        assert "3 item(s)" in result


class TestFormatResult:
    def test_none_result(self):
        assert _format_result(None) == "(no data)"

    def test_scalar_result(self):
        assert _format_result("done") == "done"

    def test_dict_with_short_list_values(self):
        result = _format_result({"deleted": True, "id": 5})
        assert "deleted=True" in result
        assert "id=5" in result

    def test_dict_with_nested_long_list_is_summarized(self):
        overdue = [{"id": i, "title": f"Task {i}"} for i in range(30)]
        result = _format_result({"overdue": overdue, "due_today": [], "overdue_count": 30})
        assert "overdue:" in result
        assert "30 item(s) total, showing 10 most recent" in result
        assert "overdue_count=30" in result

    def test_large_note_list_stays_well_under_telegram_limit(self):
        notes = [
            {"id": i, "title": f"Note {i}", "content": "lorem ipsum " * 200}
            for i in range(50)
        ]
        result = _format_result(notes)
        assert len(result) < _MAX_RESPONSE_CHARS
        assert "50 item(s) total, showing 10 most recent" in result


class TestCapResponseLength:
    def test_short_text_untouched(self):
        text = "All good, nothing to do."
        assert _cap_response_length(text) == text

    def test_long_text_truncated_with_notice(self):
        text = "a" * (_MAX_RESPONSE_CHARS + 500)
        result = _cap_response_length(text)
        assert len(result) <= _MAX_RESPONSE_CHARS
        assert result.endswith("(message truncated — too long to send)")

    def test_result_never_exceeds_telegram_limit(self):
        text = "z" * 10000
        result = _cap_response_length(text)
        assert len(result) < 4096
