"""Helpers for portal routes that proxy writes to the backend and relay its answer to the page's fetch()."""
import logging
from typing import Any

import httpx
from fastapi.responses import JSONResponse

import app.client as api

logger = logging.getLogger(__name__)


def error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    """The backend's `detail` message when it is plain text, else the fallback."""
    try:
        detail = exc.response.json().get("detail")
    except ValueError:
        return fallback
    return detail if isinstance(detail, str) else fallback


async def forward(call, fallback: str) -> JSONResponse:
    """Run a backend write and relay the result (or its error message) as JSON."""
    try:
        result = await call
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": error_detail(exc, fallback)}, status_code=exc.response.status_code)
    except httpx.HTTPError:
        return JSONResponse({"error": fallback}, status_code=502)
    return JSONResponse(result)


async def safe_get(path: str, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    """GET from the backend; an unreachable or failing backend yields `default` instead of an exception."""
    try:
        return await api.get(path, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Portal: GET %s failed: %s", path, exc)
        return default
