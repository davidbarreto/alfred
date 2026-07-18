from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.google_oauth.client import GoogleOAuthClient, GoogleTokenExpiredError


def _mock_response(json_data: dict | None = None, status_code: int = 200, content: bytes = b"{}") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.content = content
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status.side_effect = (
        httpx.HTTPStatusError("error", request=MagicMock(), response=resp) if status_code >= 400 else None
    )
    return resp


def _client() -> GoogleOAuthClient:
    return GoogleOAuthClient(
        provider="google_contacts",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
    )


class TestRequest:

    @pytest.mark.asyncio
    async def test_refreshes_access_token_lazily(self):
        client = _client()
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.post = AsyncMock(return_value=_mock_response({"access_token": "token-1"}))
            instance.request = AsyncMock(return_value=_mock_response({"ok": True}))

            result = await client._request("GET", "https://example.com/thing")

        assert result == {"ok": True}
        assert client._access_token == "token-1"
        assert instance.request.call_args.kwargs["headers"]["Authorization"] == "Bearer token-1"

    @pytest.mark.asyncio
    async def test_retries_once_on_401_by_refreshing(self):
        client = _client()
        client._access_token = "stale-token"
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.post = AsyncMock(return_value=_mock_response({"access_token": "fresh-token"}))
            instance.request = AsyncMock(
                side_effect=[_mock_response(status_code=401), _mock_response({"ok": True})]
            )

            result = await client._request("GET", "https://example.com/thing")

        assert result == {"ok": True}
        assert client._access_token == "fresh-token"
        assert instance.request.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_response_body_returns_empty_dict(self):
        client = _client()
        client._access_token = "token"
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.request = AsyncMock(return_value=_mock_response(status_code=200, content=b""))

            result = await client._request("DELETE", "https://example.com/thing")

        assert result == {}

    @pytest.mark.asyncio
    async def test_non_auth_error_raises_http_status_error(self):
        client = _client()
        client._access_token = "token"
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.request = AsyncMock(return_value=_mock_response(status_code=500))

            with pytest.raises(httpx.HTTPStatusError):
                await client._request("GET", "https://example.com/thing")


class TestRefreshAccessToken:

    @pytest.mark.asyncio
    async def test_invalid_grant_raises_token_expired_error(self):
        client = _client()
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.post = AsyncMock(
                return_value=_mock_response(
                    {"error": "invalid_grant", "error_description": "Bad Request"}, status_code=400
                )
            )

            with pytest.raises(GoogleTokenExpiredError) as exc_info:
                await client._refresh_access_token()

        assert exc_info.value.provider == "google_contacts"

    @pytest.mark.asyncio
    async def test_other_400_errors_raise_http_status_error(self):
        client = _client()
        with patch("httpx.AsyncClient") as mock_http:
            instance = mock_http.return_value.__aenter__.return_value
            instance.post = AsyncMock(
                return_value=_mock_response({"error": "invalid_client"}, status_code=400)
            )

            with pytest.raises(httpx.HTTPStatusError):
                await client._refresh_access_token()
