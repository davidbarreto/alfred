from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/shopping")

_CATEGORIES = ["grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other"]


@router.get("/", response_class=HTMLResponse)
async def shopping_page(request: Request):
    status = request.query_params.get("status", "pending")
    category = request.query_params.get("category", "all")

    try:
        items = await api.get("/organizer/shopping/", params={"status": status, "category": category, "limit": 100})
    except httpx.HTTPError:
        items = []

    return templates.TemplateResponse(request, "shopping.html", {
        "items": items,
        "active_status": status,
        "active_category": category,
        "categories": _CATEGORIES,
    })


@router.get("/list", response_class=HTMLResponse)
async def shopping_list_fragment(request: Request):
    status = request.query_params.get("status", "pending")
    category = request.query_params.get("category", "all")

    try:
        items = await api.get("/organizer/shopping/", params={"status": status, "category": category, "limit": 100})
    except httpx.HTTPError:
        items = []

    return templates.TemplateResponse(request, "_shopping_list.html", {
        "items": items,
        "categories": _CATEGORIES,
    })


@router.post("/", response_class=HTMLResponse)
async def add_shopping_item(
    request: Request,
    name: Annotated[str, Form()],
    category: Annotated[str, Form()] = "other",
    priority: Annotated[str, Form()] = "need",
):
    try:
        item = await api.post("/organizer/shopping/", json={
            "name": name,
            "category": category,
            "priority": priority,
            "source": "manual",
        })
    except httpx.HTTPError:
        return HTMLResponse("", status_code=422)

    await api.log_command("shopping.add", {"name": name, "category": category, "priority": priority}, "shopping_item", item.get("id"))
    return templates.TemplateResponse(request, "_shopping_item.html", {"item": item})


@router.post("/{item_id}/bought", response_class=HTMLResponse)
async def mark_bought(item_id: int, request: Request):
    try:
        item = await api.post(f"/organizer/shopping/{item_id}/bought/")
    except httpx.HTTPError:
        return HTMLResponse("", status_code=422)
    return templates.TemplateResponse(request, "_shopping_item.html", {"item": item})
