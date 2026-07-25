from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class BackendError(RuntimeError):
    """Raised when the Alfred backend rejects or fails a request."""


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().alfred_api_token}"}


def _url(path: str) -> str:
    base = get_settings().backend_url.rstrip("/")
    return f"{base}{path}"


async def get_catalog() -> dict[str, dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(_url("/commands/catalog"), headers=_headers(), timeout=10.0)
        resp.raise_for_status()
        return resp.json()["domains"]


async def execute_command(cmd_type: str, command: str, args: dict[str, Any]) -> Any:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _url("/commands/execute"),
            headers=_headers(),
            json={"type": cmd_type, "command": command, "args": args, "source": "mcp"},
            timeout=30.0,
        )
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        logger.error("Backend rejected %s.%s: status=%d detail=%s", cmd_type, command, resp.status_code, detail)
        raise BackendError(f"Alfred backend error ({resp.status_code}): {detail}")
    return resp.json()["result"]
