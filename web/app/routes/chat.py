from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.config import get_settings
from app.templates_config import templates

router = APIRouter(prefix="/chat")

_HISTORY_LIMIT = 50


async def _load_portal_history() -> tuple[int | None, list[dict]]:
    """Return (session_id, messages) for the active web/portal session, or (None, [])."""
    try:
        sessions = await api.get("/core/sessions/", params={"active_only": True})
        session = next(
            (s for s in sessions if s.get("source") == "web" and s.get("external_id") == "portal"),
            None,
        )
        if not session:
            return None, []
        session_id = session["id"]
        messages = await api.get("/core/messages/", params={"session_id": session_id, "limit": _HISTORY_LIMIT})
        return session_id, messages
    except httpx.HTTPError:
        return None, []


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    s = get_settings()
    _, messages = await _load_portal_history()
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
