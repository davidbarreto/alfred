import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/notes")


@router.get("/", response_class=HTMLResponse)
async def notes_page(request: Request):
    q = request.query_params.get("q", "").strip()
    tags_raw = request.query_params.getlist("tags")
    params: dict = {"limit": 100}
    if tags_raw:
        params["tags"] = tags_raw

    try:
        notes = await api.get("/organizer/notes", params=params)
    except httpx.HTTPError:
        notes = []

    if q:
        q_lower = q.lower()
        notes = [n for n in notes if q_lower in n.get("title", "").lower() or q_lower in n.get("content", "").lower()]

    return templates.TemplateResponse(request, "notes.html", {
        "notes": notes,
        "query": q,
        "active_tags": tags_raw,
    })


@router.get("/grid", response_class=HTMLResponse)
async def notes_grid_fragment(request: Request):
    q = request.query_params.get("q", "").strip()
    params: dict = {"limit": 100}

    try:
        notes = await api.get("/organizer/notes", params=params)
    except httpx.HTTPError:
        notes = []

    if q:
        q_lower = q.lower()
        notes = [n for n in notes if q_lower in n.get("title", "").lower() or q_lower in n.get("content", "").lower()]

    return templates.TemplateResponse(request, "_notes_grid.html", {"notes": notes})
