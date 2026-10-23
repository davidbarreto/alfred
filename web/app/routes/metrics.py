import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import app.client as api
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics")

_HISTORY_PAGE_SIZE = 15
_QUICK_ACTIONS = ("start", "stop", "log")
_WINDOWS = {"": "All time", "30": "Last 30 days", "90": "Last 90 days"}
_KIND_LABEL = {"duration": "timer", "value": "value", "count": "count"}


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _HISTORY_PAGE_SIZE
    return items[:_HISTORY_PAGE_SIZE], has_next, offset > 0


def _error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    try:
        detail = exc.response.json().get("detail")
    except ValueError:
        return fallback
    return detail if isinstance(detail, str) else fallback


def _seg(name: str) -> str:
    """A series name as one URL path segment, so it can never alter the backend path."""
    return quote(name, safe="")


def _int_param(raw: str | None, default: int | None = None) -> int | None:
    try:
        return max(0, int(raw)) if raw not in (None, "") else default
    except ValueError:
        return default


async def _safe_get(path: str, params: dict[str, Any] | None = None, default: Any = None) -> Any:
    try:
        return await api.get(path, params=params)
    except httpx.HTTPError as exc:
        logger.warning("Metrics portal: GET %s failed: %s", path, exc)
        return default


async def _forward(call, fallback: str) -> JSONResponse:
    """Run a backend write and relay the result (or its error message) to the page's fetch()."""
    try:
        result = await call
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": _error_detail(exc, fallback)}, status_code=exc.response.status_code)
    except httpx.HTTPError:
        return JSONResponse({"error": fallback}, status_code=502)
    return JSONResponse(result)


@router.get("", response_class=HTMLResponse)
async def metrics_page(request: Request):
    series = await _safe_get("/metrics/series")
    open_entries = await _safe_get("/metrics/entries/open", default=[])
    cards = []
    if series is not None:
        stats = await asyncio.gather(
            *[_safe_get(f"/metrics/series/{_seg(s['name'])}/stats") if s["entry_count"] else _none() for s in series]
        )
        running = {e["series_name"]: e for e in open_entries}
        cards = [{"series": s, "stats": st, "running": running.get(s["name"])} for s, st in zip(series, stats)]
    return templates.TemplateResponse(request, "metrics.html", {
        "available": series is not None,
        "cards": cards,
        "kind_label": _KIND_LABEL,
    })


async def _none() -> None:
    return None


# Static paths are registered before "/{name}" so they aren't read as a series name.

@router.post("/series")
async def create_series(request: Request):
    return await _forward(api.post("/metrics/series", json=await request.json()), "Could not create the series.")


@router.patch("/series/{name}")
async def update_series(name: str, request: Request):
    return await _forward(
        api.patch(f"/metrics/series/{_seg(name)}", json=await request.json()), "Could not update the series."
    )


@router.post("/quick/{action}")
async def quick_action(action: str, request: Request):
    if action not in _QUICK_ACTIONS:
        return JSONResponse({"error": "Unknown action."}, status_code=404)
    return await _forward(
        api.post(f"/metrics/quick/{action}", json=await request.json(), timeout=15.0),
        "Could not reach the metrics service.",
    )


@router.post("/entries")
async def create_entry(request: Request):
    return await _forward(api.post("/metrics/entries", json=await request.json()), "Could not add the entry.")


@router.post("/entries/{entry_id}/discard")
async def discard_entry(entry_id: int):
    return await _forward(api.post(f"/metrics/entries/{entry_id}/discard"), "Could not discard the entry.")


@router.get("/{name}", response_class=HTMLResponse)
async def series_page(name: str, request: Request):
    tag = request.query_params.get("tag") or None
    window = request.query_params.get("days", "")
    days = _int_param(window) or None
    series = await _safe_get(f"/metrics/series/{_seg(name)}")
    if series is None:
        return RedirectResponse("/metrics", status_code=302)
    params = {k: v for k, v in {"tag": tag, "days": days}.items() if v is not None}
    stats, open_entries, tags = await asyncio.gather(
        _safe_get(f"/metrics/series/{_seg(name)}/stats", params=params),
        _safe_get("/metrics/entries/open", default=[]),
        _safe_get("/metrics/tags", default=[]),
    )
    return templates.TemplateResponse(request, "metrics_series.html", {
        "series": series,
        "stats": stats,
        "running": next((e for e in open_entries if e["series_name"] == series["name"]), None),
        "tag_options": [t["name"] for t in tags],
        "selected_tag": tag,
        "window": window if window in _WINDOWS else "",
        "windows": _WINDOWS,
    })


@router.get("/{name}/history", response_class=HTMLResponse)
async def history_section(name: str, request: Request):
    offset = _int_param(request.query_params.get("offset"), 0) or 0
    tag = request.query_params.get("tag") or None
    params = {"series": name, "limit": _HISTORY_PAGE_SIZE + 1, "offset": offset}
    if tag:
        params["tag"] = tag
    raw = await _safe_get("/metrics/entries", params=params, default=[])
    entries, has_next, has_prev = _pagination(raw or [], offset)
    series = await _safe_get(f"/metrics/series/{_seg(name)}") or {"name": name, "kind": "duration", "unit": None}
    return templates.TemplateResponse(request, "_metrics_history.html", {
        "series": series,
        "entries": entries,
        "history_offset": offset,
        "history_has_next": has_next,
        "history_has_prev": has_prev,
        "page_size": _HISTORY_PAGE_SIZE,
        "tag": tag or "",
    })
