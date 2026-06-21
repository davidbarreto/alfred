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


@router.post("/message")
async def send_message(
    request: Request,
    message: Annotated[str, Form()],
):
    """Ingests the user message and returns the session_id for the SSE call."""
    try:
        result = await api.post("/core/messages", json={
            "text": message,
            "source": "web",
            "external_id": "portal",
            "meta": {},
        })
        return {"session_id": result["session_id"]}
    except httpx.HTTPError as exc:
        return HTMLResponse(f"Failed to send: {exc}", status_code=422)
