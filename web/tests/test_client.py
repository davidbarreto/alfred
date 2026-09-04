import httpx

import app.client as api


class _EmptyBodyTransport(httpx.AsyncBaseTransport):
    """Simulates a backend 201/204 response with no body, e.g. FastAPI's
    `Response(status_code=201)` on the interview-stage link endpoints."""

    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self._status_code, request=request)


_RealAsyncClient = httpx.AsyncClient


def _patch_transport(monkeypatch, status_code: int) -> None:
    def _client_factory(*args, **kwargs):
        kwargs["transport"] = _EmptyBodyTransport(status_code)
        return _RealAsyncClient(*args, **kwargs)

    monkeypatch.setattr(api.httpx, "AsyncClient", _client_factory)


class TestPostHandlesEmptyBody:
    """Regression test: `api.post` previously called `resp.json()` unconditionally,
    which raised JSONDecodeError against a real backend 201-with-no-body response
    (e.g. POST /organizer/interview-stages/{id}/contacts/{id}), surfacing as a portal
    500 whenever a route linked a contact/task/note to a stage."""

    async def test_returns_none_for_201_with_no_body(self, monkeypatch):
        _patch_transport(monkeypatch, 201)
        result = await api.post("/some/path", json={"role": "recruiter"})
        assert result is None

    async def test_returns_none_for_204_with_no_body(self, monkeypatch):
        _patch_transport(monkeypatch, 204)
        result = await api.patch("/some/path", json={"x": 1})
        assert result is None


class TestPostStillParsesJsonBody:
    async def test_returns_parsed_json_when_present(self, monkeypatch):
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": 1}, request=request)

        def _client_factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_handler)
            return _RealAsyncClient(*args, **kwargs)

        monkeypatch.setattr(api.httpx, "AsyncClient", _client_factory)
        result = await api.post("/some/path", json={})
        assert result == {"id": 1}
