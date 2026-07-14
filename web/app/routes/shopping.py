import logging
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping")

_CATEGORIES = ["grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other"]


@router.get("/", response_class=HTMLResponse)
async def shopping_page(request: Request):
    status = request.query_params.get("status", "pending")
    category = request.query_params.get("category", "all")

    items, wishlist, frequent_items = [], [], []
    api_error: str | None = None
    try:
        items = await api.get("/organizer/shopping", params={"status": status, "category": category, "limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping items: error=%s", e)
        api_error = f"Cannot reach backend: {e}"

    try:
        wishlist = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load wishlist items: error=%s", e)
        api_error = api_error or f"Cannot reach backend: {e}"

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": 15})
    except httpx.HTTPError as e:
        logger.error("Failed to load frequent shopping items: error=%s", e)
        api_error = api_error or f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "shopping.html", {
        "items": items,
        "wishlist": wishlist,
        "frequent_items": frequent_items,
        "active_status": status,
        "active_category": category,
        "categories": _CATEGORIES,
        "api_error": api_error,
    })


@router.get("/list", response_class=HTMLResponse)
async def shopping_list_fragment(request: Request):
    status = request.query_params.get("status", "pending")
    category = request.query_params.get("category", "all")

    try:
        items = await api.get("/organizer/shopping", params={"status": status, "category": category, "limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping items: error=%s", e)
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
    quantity: Annotated[Optional[str], Form()] = None,
    unit: Annotated[Optional[str], Form()] = None,
    estimated_price: Annotated[Optional[str], Form()] = None,
    brand: Annotated[Optional[str], Form()] = None,
    store: Annotated[Optional[str], Form()] = None,
    url: Annotated[Optional[str], Form()] = None,
    notes: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "category": category, "priority": priority, "source": "manual"}
    if quantity:
        payload["quantity"] = quantity
    if unit:
        payload["unit"] = unit
    if estimated_price:
        payload["estimated_price"] = estimated_price
    if brand:
        payload["brand"] = brand
    if store:
        payload["store"] = store
    if url:
        payload["url"] = url
    if notes:
        payload["notes"] = notes
    try:
        item = await api.post("/organizer/shopping", json=payload)
    except httpx.HTTPError as e:
        logger.error("Failed to create shopping item: name=%r error=%s", name, e)
        return HTMLResponse("", status_code=422)

    await api.log_command("shopping.add", {"name": name, "category": category, "priority": priority}, "shopping_item", item.get("id"))

    status = request.query_params.get("status", "pending")
    list_category = request.query_params.get("category", "all")
    try:
        items = await api.get("/organizer/shopping", params={"status": status, "category": list_category, "limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to reload shopping items after create: error=%s", e)
        items = []

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": 15})
    except httpx.HTTPError as e:
        logger.error("Failed to reload frequent shopping items after create: error=%s", e)
        frequent_items = []

    list_html = templates.env.get_template("_shopping_list.html").render({
        "items": items,
        "categories": _CATEGORIES,
    })
    frequent_html = templates.env.get_template("_shopping_frequent.html").render({
        "frequent_items": frequent_items,
        "oob": True,
    })
    return HTMLResponse(list_html + frequent_html)


@router.post("/{item_id}/bought", response_class=HTMLResponse)
async def mark_bought(item_id: int, request: Request):
    try:
        item = await api.post(f"/organizer/shopping/{item_id}/bought")
    except httpx.HTTPError as e:
        logger.error("Failed to mark shopping item bought: id=%d error=%s", item_id, e)
        return HTMLResponse("", status_code=422)
    return templates.TemplateResponse(request, "_shopping_item.html", {"item": item})


# --- Wishlist ---

@router.get("/wishlist", response_class=HTMLResponse)
async def wishlist_fragment(request: Request):
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load wishlist items: error=%s", e)
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
    except httpx.HTTPError as e:
        logger.error("Failed to create wishlist item: name=%r error=%s", name, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to add to wishlist.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to reload wishlist items after create: error=%s", e)
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})


@router.delete("/wishlist/{item_id}", response_class=HTMLResponse)
async def delete_wishlist_item(item_id: int, request: Request):
    try:
        await api.delete(f"/organizer/wishlist/{item_id}")
    except httpx.HTTPError as e:
        logger.error("Failed to delete wishlist item: id=%d error=%s", item_id, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete item.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to reload wishlist items after delete: error=%s", e)
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})


@router.post("/wishlist/{item_id}/promote", response_class=HTMLResponse)
async def promote_wishlist_item(item_id: int, request: Request):
    try:
        await api.post(f"/organizer/wishlist/{item_id}/promote", json={"category": "other"})
    except httpx.HTTPError as e:
        logger.error("Failed to promote wishlist item: id=%d error=%s", item_id, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to promote item.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to reload wishlist items after promote: error=%s", e)
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories": _CATEGORIES})
