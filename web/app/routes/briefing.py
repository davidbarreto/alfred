import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/briefing")

_PAGE_SIZE = 20


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


def _history_params(type: str | None, offset: int) -> dict:
    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    if type:
        params["type"] = type
    return params


@router.get("/", response_class=HTMLResponse)
async def briefing_page(request: Request):
    api_error: str | None = None
    briefing = None

    try:
        briefing = await api.get("/briefing/morning")
    except httpx.HTTPStatusError as e:
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        api_error = f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "briefing.html", {
        "briefing": briefing,
        "api_error": api_error,
    })


@router.get("/formatted", response_class=HTMLResponse)
async def briefing_formatted_fragment(request: Request, force: bool = False):
    try:
        result = await api.get("/briefing/morning/formatted", params={"force": force})
        text = result.get("text", "")
    except httpx.HTTPError:
        text = None

    return templates.TemplateResponse(request, "_briefing_formatted.html", {"text": text})


@router.get("/evening", response_class=HTMLResponse)
async def evening_digest_page(request: Request):
    api_error: str | None = None
    digest = None

    try:
        digest = await api.get("/briefing/evening")
    except httpx.HTTPStatusError as e:
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        api_error = f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "evening_digest.html", {
        "digest": digest,
        "api_error": api_error,
    })


@router.get("/evening/formatted", response_class=HTMLResponse)
async def evening_digest_formatted_fragment(request: Request, force: bool = False):
    text = None
    generated = True

    try:
        result = await api.get("/briefing/evening/formatted", params={"force": force})
        text = result.get("text", "")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            generated = False
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(request, "_briefing_formatted.html", {"text": text, "generated": generated})


@router.get("/history", response_class=HTMLResponse)
async def briefing_history_page(request: Request, type: str | None = None):
    api_error: str | None = None
    items: list = []
    has_next = has_prev = False

    try:
        raw = await api.get("/briefing/history", params=_history_params(type, 0))
        items, has_next, has_prev = _pagination(raw, 0)
    except httpx.HTTPStatusError as e:
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        api_error = f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "briefing_history.html", {
        "items": items,
        "history_offset": 0,
        "history_has_next": has_next,
        "history_has_prev": has_prev,
        "type_filter": type,
        "api_error": api_error,
    })


@router.get("/history/list", response_class=HTMLResponse)
async def briefing_history_list_fragment(request: Request, type: str | None = None, offset: int = 0):
    api_error: str | None = None
    items: list = []
    has_next = has_prev = False

    try:
        raw = await api.get("/briefing/history", params=_history_params(type, offset))
        items, has_next, has_prev = _pagination(raw, offset)
    except httpx.HTTPError as e:
        api_error = f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "_briefing_history_list.html", {
        "items": items,
        "history_offset": offset,
        "history_has_next": has_next,
        "history_has_prev": has_prev,
        "type_filter": type,
        "api_error": api_error,
    })
