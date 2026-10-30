from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().alfred_api_token}", "X-Alfred-Client": "web"}


def _url(path: str) -> str:
    base = get_settings().backend_url.rstrip("/")
    return f"{base}{path}"


_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    """One shared client so requests reuse pooled keep-alive connections to the backend."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(follow_redirects=True)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    resp = await _http().get(_url(path), headers=_headers(), params=params, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def get_bytes(path: str, params: dict[str, Any] | None = None) -> tuple[bytes, str]:
    resp = await _http().get(_url(path), headers=_headers(), params=params, timeout=10.0)
    resp.raise_for_status()
    return resp.content, resp.headers.get("content-type", "application/octet-stream")


async def post_multipart(
    path: str,
    data: dict[str, Any] | None = None,
    files: dict[str, tuple[str, bytes, str]] | None = None,
) -> Any:
    resp = await _http().post(_url(path), headers=_headers(), data=data, files=files, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def post(path: str, json: Any = None, timeout: float = 10.0) -> Any:
    resp = await _http().post(_url(path), headers=_headers(), json=json, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.content else None


async def patch(path: str, json: Any = None, timeout: float = 10.0) -> Any:
    resp = await _http().patch(_url(path), headers=_headers(), json=json, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if resp.content else None


async def put(path: str, json: Any = None) -> Any:
    resp = await _http().put(_url(path), headers=_headers(), json=json, timeout=10.0)
    resp.raise_for_status()
    return resp.json() if resp.content else None


async def delete(path: str) -> None:
    resp = await _http().delete(_url(path), headers=_headers(), timeout=10.0)
    resp.raise_for_status()
