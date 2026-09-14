from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter()


def _humanize(paused_at: str | None) -> str | None:
    if paused_at is None:
        return None
    return datetime.fromisoformat(paused_at).strftime("%d %b, %H:%M")


def _render(
    request: Request,
    paused: bool,
    paused_at: str | None = None,
    result: dict | None = None,
    error: str | None = None,
):
    return templates.TemplateResponse(request, "_pause_control.html", {
        "paused": paused,
        "paused_at": _humanize(paused_at),
        "result": result,
        "error": error,
    })


@router.get("/pause/control", response_class=HTMLResponse)
async def pause_control(request: Request):
    state = await api.get("/core/pause")
    return _render(request, state["paused"], state["paused_at"])


@router.post("/pause", response_class=HTMLResponse)
async def start_pause(request: Request):
    try:
        state = await api.post("/core/pause")
    except httpx.HTTPStatusError as exc:
        state = await api.get("/core/pause")
        return _render(request, state["paused"], state["paused_at"], error=_error_detail(exc))
    return _render(request, state["paused"], state["paused_at"])


@router.post("/pause/resume", response_class=HTMLResponse)
async def stop_pause(request: Request):
    try:
        result = await api.post("/core/pause/resume")
    except httpx.HTTPStatusError as exc:
        state = await api.get("/core/pause")
        return _render(request, state["paused"], state["paused_at"], error=_error_detail(exc))
    return _render(request, paused=False, result=result)


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return exc.response.json().get("detail", "Something went wrong. Please try again.")
    except ValueError:
        return "Something went wrong. Please try again."
