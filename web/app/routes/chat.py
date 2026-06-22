from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.config import get_settings
from app.templates_config import templates

router = APIRouter(prefix="/chat")

_HISTORY_LIMIT = 50


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    s = get_settings()
    try:
        messages = await api.get(
            "/core/messages/",
            params={"source": "web", "external_id": "portal", "limit": _HISTORY_LIMIT},
        )
    except httpx.HTTPError:
        messages = []
    return templates.TemplateResponse(request, "chat.html", {
        "backend_url": s.public_backend_url,
        "api_token": s.alfred_api_token,
        "initial_messages": messages,
    })


@router.post("/message")
async def send_message(
    request: Request,
    message: Annotated[str, Form()],
):
    """Ingests the user message and returns the session_id for the SSE call."""
    try:
        result = await api.post("/core/messages/", json={
            "text": message,
            "source": "web",
            "external_id": "portal",
            "meta": {},
        })
        return {"session_id": result["session_id"]}
    except httpx.HTTPError as exc:
        return HTMLResponse(f"Failed to send: {exc}", status_code=422)
