import httpx
import pytest

from app.shared.forward import error_detail, forward, safe_get


def _status_error(status: int, body) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://api/x")
    return httpx.HTTPStatusError("boom", request=request, response=httpx.Response(status, json=body, request=request))


class TestErrorDetail:
    def test_plain_text_detail_is_relayed(self):
        assert error_detail(_status_error(409, {"detail": "Already exists"}), "fallback") == "Already exists"

    def test_validation_error_lists_fall_back(self):
        assert error_detail(_status_error(422, {"detail": [{"msg": "bad"}]}), "fallback") == "fallback"

    def test_non_json_body_falls_back(self):
        request = httpx.Request("POST", "http://api/x")
        exc = httpx.HTTPStatusError("boom", request=request, response=httpx.Response(500, text="oops", request=request))
        assert error_detail(exc, "fallback") == "fallback"


class TestForward:
    async def test_success_is_relayed(self):
        async def call():
            return {"id": 1}

        response = await forward(call(), "fallback")
        assert response.status_code == 200 and response.body == b'{"id":1}'

    async def test_backend_error_keeps_status_and_message(self):
        async def call():
            raise _status_error(409, {"detail": "Taken"})

        response = await forward(call(), "fallback")
        assert response.status_code == 409 and b"Taken" in response.body

    async def test_unreachable_backend_is_a_502_with_the_fallback(self):
        async def call():
            raise httpx.ConnectError("down")

        response = await forward(call(), "Could not save.")
        assert response.status_code == 502 and b"Could not save." in response.body


class TestSafeGet:
    async def test_returns_the_payload(self, mock_api):
        mock_api["get"].return_value = [1]
        assert await safe_get("/x", params={"a": 1}) == [1]
        mock_api["get"].assert_awaited_once_with("/x", params={"a": 1})

    @pytest.mark.parametrize("default", [None, []])
    async def test_failure_returns_the_default(self, mock_api, default):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        assert await safe_get("/x", default=default) == default
