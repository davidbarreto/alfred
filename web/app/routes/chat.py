from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.config import get_settings
from app.templates_config import templates

router = APIRouter(prefix="/chat")


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    s = get_settings()
    return templates.TemplateResponse(request, "chat.html", {
        "backend_url": s.public_backend_url,
        "api_token": s.alfred_api_token,
    })


@router.post("/message", response_class=HTMLResponse)
async def send_message(
    request: Request,
    session_id: Annotated[int, Form()],
    message: Annotated[str, Form()],
):
    """Creates the user message in the backend, returns the session_id for the SSE call."""
    try:
        await api.post("/core/messages", json={
            "text": message,
            "source": "portal",
            "external_id": None,
            "meta": {},
        })
    except httpx.HTTPError as exc:
        return HTMLResponse(f'<div class="text-error">Failed to send: {exc}</div>', status_code=422)

    # Return the session_id so the JS can open the SSE stream
    return HTMLResponse(str(session_id))


@router.post("/session", response_class=HTMLResponse)
async def create_session(request: Request):
    """Creates a new chat session and returns its id."""
    try:
        session = await api.post("/core/sessions", json={"source": "portal"})
        return HTMLResponse(str(session["id"]))
    except httpx.HTTPError as exc:
        return HTMLResponse(f'<div class="text-error">Failed: {exc}</div>', status_code=422)
