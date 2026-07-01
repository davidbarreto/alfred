from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().alfred_api_token}"}


def _url(path: str) -> str:
    base = get_settings().backend_url.rstrip("/")
    return f"{base}{path}"


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(_url(path), headers=_headers(), params=params, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def post(path: str, json: Any = None) -> Any:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(_url(path), headers=_headers(), json=json, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def patch(path: str, json: Any = None) -> Any:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.patch(_url(path), headers=_headers(), json=json, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def delete(path: str) -> None:
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.delete(_url(path), headers=_headers(), timeout=10.0)
        resp.raise_for_status()


async def log_command(
    command_name: str,
    entities: dict | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    """Log a web portal action as a command execution (fire-and-forget)."""
    try:
        result = await post("/core/command-executions", json={
            "command_name": command_name,
            "entities": entities or {},
            "status": "success",
        })
        if entity_type or entity_id:
            await patch(f"/core/command-executions/{result['id']}", json={
                "entity_type": entity_type,
                "entity_id": entity_id,
            })
    except httpx.HTTPError:
        pass
