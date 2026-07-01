from typing import Annotated, Optional

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

    items, wishlist = [], []
    try:
        items = await api.get("/organizer/shopping", params={"status": status, "category": category, "limit": 100})
    except httpx.HTTPError:
        pass

    try:
        wishlist = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(request, "shopping.html", {
        "items": items,
        "wishlist": wishlist,
        "active_status": status,
        "active_category": category,
        "categories": _CATEGORIES,
    })


@router.get("/list", response_class=HTMLResponse)
async def shopping_list_fragment(request: Request):
    status = request.query_params.get("status", "pending")
    category = request.query_params.get("category", "all")

    try:
        items = await api.get("/organizer/shopping", params={"status": status, "category": category, "limit": 100})
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
        item = await api.post("/organizer/shopping", json={
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
        item = await api.post(f"/organizer/shopping/{item_id}/bought")
    except httpx.HTTPError:
        return HTMLResponse("", status_code=422)
    return templates.TemplateResponse(request, "_shopping_item.html", {"item": item})


# --- Wishlist ---

@router.get("/wishlist", response_class=HTMLResponse)
async def wishlist_fragment(request: Request):
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError:
        items = []
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})


@router.post("/wishlist", response_class=HTMLResponse)
async def add_wishlist_item(
    request: Request,
    name: Annotated[str, Form()],
    category: Annotated[str, Form()] = "other",
    estimated_price: Annotated[Optional[str], Form()] = None,
    brand: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "category": category}
    if estimated_price:
        payload["estimated_price"] = estimated_price
    if brand:
        payload["brand"] = brand
    try:
        await api.post("/organizer/wishlist", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to add to wishlist.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})


@router.delete("/wishlist/{item_id}", response_class=HTMLResponse)
async def delete_wishlist_item(item_id: int, request: Request):
    try:
        await api.delete(f"/organizer/wishlist/{item_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete item.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})


@router.post("/wishlist/{item_id}/promote", response_class=HTMLResponse)
async def promote_wishlist_item(item_id: int, request: Request):
    try:
        await api.post(f"/organizer/wishlist/{item_id}/promote", json={"category": "other"})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to promote item.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})
