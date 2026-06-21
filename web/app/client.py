from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().alfred_api_token}"}


def _base() -> str:
    return get_settings().backend_url.rstrip("/")


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{_base()}{path}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, headers=_headers(), params=params, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def post(path: str, json: Any = None) -> Any:
    url = f"{_base()}{path}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(url, headers=_headers(), json=json, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def patch(path: str, json: Any = None) -> Any:
    url = f"{_base()}{path}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.patch(url, headers=_headers(), json=json, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def delete(path: str) -> None:
    url = f"{_base()}{path}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.delete(url, headers=_headers(), timeout=10.0)
        resp.raise_for_status()
