import json

import httpx
import pytest

from app.backend_client import BackendError, execute_command, get_catalog

# Captured before any monkeypatching — the patched target is httpx.AsyncClient
# itself (same module object this test file imports), so building the mock
# client from a live `httpx.AsyncClient` reference would recurse into itself.
_RealAsyncClient = httpx.AsyncClient


def _patch_client(monkeypatch, handler):
    monkeypatch.setattr(
        "app.backend_client.httpx.AsyncClient",
        lambda *a, **kw: _RealAsyncClient(transport=httpx.MockTransport(handler)),
    )


class TestExecuteCommand:
    async def test_success_returns_result(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/commands/execute"
            payload = json.loads(request.read())
            assert payload["source"] == "mcp"
            assert payload["type"] == "task"
            assert payload["command"] == "add"
            return httpx.Response(200, json={"result": {"id": 1, "title": "Buy milk"}})

        _patch_client(monkeypatch, handler)
        result = await execute_command("task", "add", {"title": "Buy milk"})
        assert result == {"id": 1, "title": "Buy milk"}

    async def test_error_response_raises_backend_error_with_detail(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"detail": "Task search requires a query"})

        _patch_client(monkeypatch, handler)
        with pytest.raises(BackendError, match="Task search requires a query"):
            await execute_command("task", "search", {})


class TestGetCatalog:
    async def test_returns_domains(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/commands/catalog"
            return httpx.Response(200, json={"domains": {"task": {"add": {}}}})

        _patch_client(monkeypatch, handler)
        catalog = await get_catalog()
        assert catalog == {"task": {"add": {}}}


class TestClientHeader:
    """Backend API usage is charted per caller via X-Alfred-Client."""

    async def test_execute_command_identifies_as_mcp(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Alfred-Client"] == "mcp"
            return httpx.Response(200, json={"result": {}})

        _patch_client(monkeypatch, handler)
        await execute_command("task", "list", {})

    async def test_get_catalog_identifies_as_mcp(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["X-Alfred-Client"] == "mcp"
            return httpx.Response(200, json={"domains": {}})

        _patch_client(monkeypatch, handler)
        await get_catalog()
