from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_REJECTED_STATUSES = (400, 403)


class GoogleTokenExpiredError(Exception):
    """The stored refresh token for a Google OAuth provider was rejected (invalid_grant).

    Re-authorization (a fresh consent flow) is required; retrying cannot recover this.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"Google OAuth refresh token expired or revoked for provider={provider!r}")


def _google_error_message(response: httpx.Response | None) -> str | None:
    """Google's own explanation (`error.message`) when the body carries one, else None."""
    if response is None:
        return None
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return None
    return message if isinstance(message, str) and message.strip() else None


class GoogleRequestRejectedError(httpx.HTTPStatusError):
    """Google refused a data request (HTTP 400/403): the change is not allowed, retrying cannot help.

    `reason` is Google's own `error.message` when the body has one.
    Subclasses `httpx.HTTPStatusError` so existing handlers keep working.
    """

    def __init__(self, provider: str, status_code: int, response: httpx.Response | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        self.reason = _google_error_message(response)
        message = f"Google rejected the {provider!r} request with HTTP {status_code}"
        super().__init__(message, request=getattr(response, "request", None), response=response)  # type: ignore[arg-type]


class GoogleOAuthClient:
    """Base for Google API clients authenticated via a stored OAuth refresh token.

    Handles lazy access-token fetch and a single auto-refresh-and-retry on 401.
    """

    def __init__(self, provider: str, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._provider = provider
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None

    def _raise(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error("%s API error %s: %s", self._provider, response.status_code, response.text)
            response.raise_for_status()

    async def _refresh_access_token(self) -> str:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            if resp.status_code == 400:
                try:
                    is_invalid_grant = resp.json().get("error") == "invalid_grant"
                except ValueError:
                    is_invalid_grant = False
                if is_invalid_grant:
                    logger.error("Google OAuth refresh token rejected: provider=%s", self._provider)
                    raise GoogleTokenExpiredError(self._provider)
            self._raise(resp)
            return resp.json()["access_token"]

    async def _headers(self) -> dict[str, str]:
        if self._access_token is None:
            self._access_token = await self._refresh_access_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 401:
                self._access_token = await self._refresh_access_token()
                headers = {"Authorization": f"Bearer {self._access_token}"}
                resp = await http.request(method, url, headers=headers, **kwargs)
            if resp.status_code in _REJECTED_STATUSES:
                logger.error("%s API error %s: %s", self._provider, resp.status_code, resp.text)
                raise GoogleRequestRejectedError(self._provider, resp.status_code, resp)
            self._raise(resp)
            return {} if not resp.content else resp.json()
