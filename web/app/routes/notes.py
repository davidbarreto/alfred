from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/notes")

_PAGE_SIZE = 24
_WRITE_TIMEOUT = 30.0  # Notion sync + embedding generation run synchronously on the backend


def _build_params(tags: list[str], sort: str, archived: bool, offset: int) -> dict:
    params: dict = {
        "limit": _PAGE_SIZE + 1,
        "offset": offset,
        "sort": sort,
        "archived": "true" if archived else "false",
    }
    if tags:
        params["tags"] = tags
    return params


def _pagination(notes: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(notes) > _PAGE_SIZE
    return notes[:_PAGE_SIZE], has_next, offset > 0


def _parse_query(request: Request) -> tuple[list[str], str, int]:
    tags = request.query_params.getlist("tags")
    sort = request.query_params.get("sort", "created")
    offset = max(0, int(request.query_params.get("offset", "0")))
    return tags, sort, offset


def _parse_archived(request: Request) -> bool:
    return request.query_params.get("archived", "false") == "true"


async def _fetch_notes(tags: list[str], sort: str, archived: bool, offset: int) -> list[dict]:
    try:
        return await api.get("/organizer/notes", params=_build_params(tags, sort, archived, offset))
    except httpx.HTTPError:
        return []


async def _fetch_all_tags(archived: bool) -> list[str]:
    try:
        raw = await api.get(
            "/organizer/notes",
            params={"limit": 200, "archived": "true" if archived else "false"},
        )
    except httpx.HTTPError:
        raw = []
    return sorted({tag for note in raw for tag in (note.get("tags") or [])})


async def _grid_context(tags: list[str], sort: str, archived: bool, offset: int) -> dict:
    raw = await _fetch_notes(tags, sort, archived, offset)
    notes, has_next, has_prev = _pagination(raw, offset)
    return {
        "notes": notes,
        "has_next": has_next,
        "has_prev": has_prev,
        "archived_view": archived,
        "query_tags": tags,
        "query_sort": sort,
        "query_offset": offset,
    }


async def _page_context(request: Request, archived: bool) -> dict:
    tags, sort, offset = _parse_query(request)
    context = await _grid_context(tags, sort, archived, offset)
    context["available_tags"] = await _fetch_all_tags(archived)
    context["page_size"] = _PAGE_SIZE
    return context


@router.get("/", response_class=HTMLResponse)
async def notes_page(request: Request):
    context = await _page_context(request, archived=False)
    return templates.TemplateResponse(request, "notes.html", context)


@router.get("/grid", response_class=HTMLResponse)
async def notes_grid_fragment(request: Request):
    tags, sort, offset = _parse_query(request)
    context = await _grid_context(tags, sort, False, offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.get("/archived", response_class=HTMLResponse)
async def archived_notes_page(request: Request):
    context = await _page_context(request, archived=True)
    return templates.TemplateResponse(request, "archived_notes.html", context)


@router.get("/archived/grid", response_class=HTMLResponse)
async def archived_notes_grid_fragment(request: Request):
    tags, sort, offset = _parse_query(request)
    context = await _grid_context(tags, sort, True, offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.post("/", response_class=HTMLResponse)
async def create_note(
    request: Request,
    title: Annotated[str, Form()],
    content: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        note = await api.post(
            "/organizer/notes",
            json={"title": title, "content": content, "tags": tag_list},
            timeout=_WRITE_TIMEOUT,
        )
    except httpx.HTTPStatusError as exc:
        detail = "Failed to save note."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return Response(detail, status_code=422, media_type="text/plain")
    except httpx.HTTPError:
        return Response("Failed to save note.", status_code=422, media_type="text/plain")

    await api.log_command("note.add", {"title": title, "tags": tag_list}, "note", note.get("id"))
    context = await _grid_context([], "created", False, 0)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.patch("/{note_id}", response_class=HTMLResponse)
async def update_note(
    note_id: int,
    request: Request,
    title: Annotated[str, Form()],
    content: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        note = await api.patch(
            f"/organizer/notes/{note_id}",
            json={"title": title, "content": content, "tags": tag_list},
            timeout=_WRITE_TIMEOUT,
        )
    except httpx.HTTPStatusError as exc:
        detail = "Failed to update note."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return Response(detail, status_code=422, media_type="text/plain")
    except httpx.HTTPError:
        return Response("Failed to update note.", status_code=422, media_type="text/plain")

    await api.log_command("note.update", {"title": title, "tags": tag_list}, "note", note.get("id"))
    tags_q, sort, offset = _parse_query(request)
    context = await _grid_context(tags_q, sort, _parse_archived(request), offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.delete("/{note_id}", response_class=HTMLResponse)
async def delete_note(note_id: int, request: Request):
    try:
        await api.delete(f"/organizer/notes/{note_id}")
    except httpx.HTTPStatusError as exc:
        detail = "Failed to delete note."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return Response(detail, status_code=422, media_type="text/plain")
    except httpx.HTTPError:
        return Response("Failed to delete note.", status_code=422, media_type="text/plain")

    tags_q, sort, offset = _parse_query(request)
    context = await _grid_context(tags_q, sort, _parse_archived(request), offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.post("/{note_id}/archive", response_class=HTMLResponse)
async def archive_note(note_id: int, request: Request):
    try:
        await api.post(f"/organizer/notes/{note_id}/archive")
    except httpx.HTTPError:
        return Response("Failed to archive note.", status_code=422, media_type="text/plain")

    tags_q, sort, offset = _parse_query(request)
    context = await _grid_context(tags_q, sort, False, offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)


@router.post("/{note_id}/unarchive", response_class=HTMLResponse)
async def unarchive_note(note_id: int, request: Request):
    try:
        await api.post(f"/organizer/notes/{note_id}/unarchive")
    except httpx.HTTPError:
        return Response("Failed to unarchive note.", status_code=422, media_type="text/plain")

    tags_q, sort, offset = _parse_query(request)
    context = await _grid_context(tags_q, sort, True, offset)
    return templates.TemplateResponse(request, "_notes_grid.html", context)
