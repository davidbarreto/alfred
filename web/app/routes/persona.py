from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.templates_config import templates

router = APIRouter(prefix="/persona")


@router.get("", response_class=HTMLResponse)
async def persona_page(request: Request):
    settings = await safe_get("/core/assistant-settings")
    return templates.TemplateResponse(request, "persona.html", {"settings": settings})


@router.put("")
async def update_persona(request: Request):
    return await forward(
        api.put("/core/assistant-settings", json=await request.json()), "Could not save the persona."
    )
