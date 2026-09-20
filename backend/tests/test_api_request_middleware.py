import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from app.api.request_logging import ApiRequestLoggingMiddleware
from app.api.request_logging import _record_to_db as real_record_to_db  # bound before conftest's autouse stub


def _build(recorder: AsyncMock) -> TestClient:
    app = FastAPI()
    app.add_middleware(ApiRequestLoggingMiddleware, recorder=recorder)

    @app.get("/tasks/{task_id}")
    def get_task(task_id: int):
        return {"id": task_id}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/core/api-requests/summary")
    def summary():
        return {}

    @app.get("/missing-thing")
    def denied():
        raise HTTPException(status_code=403)

    @app.get("/boom")
    def boom():
        raise RuntimeError("boom")

    @app.get("/stream")
    def stream():
        return StreamingResponse(iter([b"a", b"b"]), media_type="text/plain")

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def recorder():
    return AsyncMock()


@pytest.fixture
def client(recorder):
    return _build(recorder)


class TestRecording:
    def test_records_client_route_template_and_status(self, client, recorder):
        response = client.get("/tasks/42", headers={"X-Alfred-Client": "web"})

        assert response.status_code == 200
        recorder.assert_awaited_once()
        kwargs = recorder.call_args.kwargs
        assert kwargs["client"] == "web"
        assert kwargs["method"] == "GET"
        assert kwargs["route"] == "/tasks/{task_id}"
        assert kwargs["status_code"] == 200
        assert kwargs["duration_ms"] >= 0

    def test_missing_header_is_passed_as_none(self, client, recorder):
        client.get("/tasks/1")

        assert recorder.call_args.kwargs["client"] is None

    def test_empty_header_is_passed_through_for_normalisation(self, client, recorder):
        client.get("/tasks/1", headers={"X-Alfred-Client": ""})

        assert not recorder.call_args.kwargs["client"]

    def test_records_error_responses(self, client, recorder):
        client.get("/missing-thing", headers={"X-Alfred-Client": "n8n"})

        assert recorder.call_args.kwargs["status_code"] == 403
        assert recorder.call_args.kwargs["client"] == "n8n"

    def test_unmatched_path_uses_placeholder_route(self, client, recorder):
        response = client.get("/wp-admin/setup.php")

        assert response.status_code == 404
        assert recorder.call_args.kwargs["route"] == "<unmatched>"
        assert recorder.call_args.kwargs["status_code"] == 404

    def test_unhandled_exception_recorded_as_500(self, client, recorder):
        response = client.get("/boom", headers={"X-Alfred-Client": "web"})

        assert response.status_code == 500
        assert recorder.call_args.kwargs["status_code"] == 500

    def test_streaming_response_is_recorded_and_intact(self, client, recorder):
        response = client.get("/stream", headers={"X-Alfred-Client": "web"})

        assert response.content == b"ab"
        assert recorder.call_args.kwargs["route"] == "/stream"


class TestExclusions:
    @pytest.mark.parametrize("path", ["/health", "/core/api-requests/summary"])
    def test_excluded_paths_are_not_recorded(self, client, recorder, path):
        client.get(path)

        recorder.assert_not_awaited()

    def test_options_preflight_is_not_recorded(self, client, recorder):
        client.options("/tasks/1")

        recorder.assert_not_awaited()


class TestFailureIsolation:
    def test_recorder_failure_does_not_break_the_request(self, recorder, caplog):
        recorder.side_effect = RuntimeError("db down")
        client = _build(recorder)

        with caplog.at_level(logging.WARNING):
            response = client.get("/tasks/1", headers={"X-Alfred-Client": "web"})

        assert response.status_code == 200
        assert response.json() == {"id": 1}
        assert "API request logging failed" in caplog.text


class TestDefaultRecorder:
    async def test_writes_through_service_in_its_own_session(self, monkeypatch):
        from unittest.mock import MagicMock

        from app.api import request_logging

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value="session")
        session_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(request_logging, "async_session", MagicMock(return_value=session_cm))
        service = MagicMock()
        service.record = AsyncMock()
        service_cls = MagicMock(return_value=service)
        monkeypatch.setattr(request_logging, "ApiRequestService", service_cls)

        await real_record_to_db(
            client="web", method="GET", route="/x", status_code=200, duration_ms=3
        )

        service_cls.assert_called_once_with("session")
        service.record.assert_awaited_once_with(
            client="web", method="GET", route="/x", status_code=200, duration_ms=3
        )


class TestAppWiring:
    """The real app must log rejected requests too, tagged with their caller."""

    def test_rejected_unauthenticated_request_is_logged_with_caller(self, monkeypatch):
        from app.main import app

        recorder = AsyncMock()
        monkeypatch.setattr("app.api.request_logging._record_to_db", recorder)

        response = TestClient(app).get("/core/pause", headers={"X-Alfred-Client": "n8n"})

        assert response.status_code == 403
        assert recorder.call_args.kwargs["client"] == "n8n"
        assert recorder.call_args.kwargs["route"] == "/core/pause"
        assert recorder.call_args.kwargs["status_code"] == 403

    def test_health_check_is_not_logged(self, monkeypatch):
        from app.main import app

        recorder = AsyncMock()
        monkeypatch.setattr("app.api.request_logging._record_to_db", recorder)

        TestClient(app).get("/health")

        recorder.assert_not_awaited()
