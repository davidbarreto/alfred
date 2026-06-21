from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
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


@router.post("/", response_class=HTMLResponse)
async def create_note(
    request: Request,
    title: Annotated[str, Form()],
    content: Annotated[str, Form()] = "",
    tags_raw: Annotated[str, Form(alias="tags")] = "",
):
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    try:
        await api.post("/organizer/notes", json={"title": title, "content": content, "tags": tags})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create note.</p>', status_code=422)

    notes = []
    try:
        notes = await api.get("/organizer/notes", params={"limit": 100})
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_notes_grid.html", {"notes": notes})
