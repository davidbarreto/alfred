import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/briefing")


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
async def briefing_formatted_fragment(request: Request):
    try:
        result = await api.get("/briefing/morning/formatted")
        text = result.get("text", "")
    except httpx.HTTPError:
        text = None

    return templates.TemplateResponse(request, "_briefing_formatted.html", {"text": text})
