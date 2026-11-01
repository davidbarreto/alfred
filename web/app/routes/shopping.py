import logging
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.shared.forward import error_detail
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping")

_FREQUENT_LIMIT = 5


async def _get_categories() -> list[dict]:
    try:
        return await api.get("/organizer/shopping-categories")
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping categories: error=%s", e)
        return []


def _shopping_list_params(status: str, category_id: str | None, limit: int = 100) -> dict:
    params: dict = {"status": status, "limit": limit}
    if category_id:
        params["category_id"] = category_id
    return params


@router.get("/", response_class=HTMLResponse)
async def shopping_page(request: Request):
    status = request.query_params.get("status", "pending")
    category_id = request.query_params.get("category_id")

    items, wishlist, frequent_items, due_recurrences = [], [], [], []
    api_error: str | None = None
    try:
        items = await api.get("/organizer/shopping", params=_shopping_list_params(status, category_id))
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping items: error=%s", e)
        api_error = f"Cannot reach backend: {e}"

    try:
        wishlist = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load wishlist items: error=%s", e)
        api_error = api_error or f"Cannot reach backend: {e}"

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": _FREQUENT_LIMIT})
    except httpx.HTTPError as e:
        logger.error("Failed to load frequent shopping items: error=%s", e)
        api_error = api_error or f"Cannot reach backend: {e}"

    try:
        due_recurrences = await api.get("/organizer/recurrence/due")
    except httpx.HTTPError as e:
        logger.error("Failed to load due recurring items: error=%s", e)
        api_error = api_error or f"Cannot reach backend: {e}"

    categories = await _get_categories()
    products = await _get_products()

    return templates.TemplateResponse(request, "shopping.html", {
        "products": products,
        "items": items,
        "wishlist": wishlist,
        "frequent_items": frequent_items,
        "due_recurrences": due_recurrences,
        "active_status": status,
        "active_category_id": int(category_id) if category_id else None,
        "categories": categories,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
        "api_error": api_error,
    })


@router.get("/names", response_class=HTMLResponse)
async def shopping_name_suggestions(request: Request):
    query = request.query_params.get("name", "").strip()
    if not query:
        return templates.TemplateResponse(request, "_shopping_name_suggestions.html", {"suggestions": []})

    try:
        suggestions = await api.get("/organizer/shopping/names", params={"q": query, "limit": 8})
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping name suggestions: q=%r error=%s", query, e)
        suggestions = []

    return templates.TemplateResponse(request, "_shopping_name_suggestions.html", {"suggestions": suggestions})


@router.get("/list", response_class=HTMLResponse)
async def shopping_list_fragment(request: Request):
    status = request.query_params.get("status", "pending")
    category_id = request.query_params.get("category_id")

    try:
        items = await api.get("/organizer/shopping", params=_shopping_list_params(status, category_id))
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping items: error=%s", e)
        items = []

    categories = await _get_categories()

    return templates.TemplateResponse(request, "_shopping_list.html", {
        "items": items,
        "categories_by_id": {c["id"]: c["name"] for c in categories},
    })


@router.post("/", response_class=HTMLResponse)
async def add_shopping_item(
    request: Request,
    name: Annotated[str, Form()],
    category_id: Annotated[int, Form()],
    priority: Annotated[str, Form()] = "need",
    quantity: Annotated[Optional[str], Form()] = None,
    unit: Annotated[Optional[str], Form()] = None,
    estimated_price: Annotated[Optional[str], Form()] = None,
    brand: Annotated[Optional[str], Form()] = None,
    store: Annotated[Optional[str], Form()] = None,
    url: Annotated[Optional[str], Form()] = None,
    notes: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "category_id": category_id, "priority": priority, "source": "manual"}
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
    add_error = ""
    try:
        await api.post("/organizer/shopping", json=payload)
    except httpx.HTTPStatusError as e:
        # e.g. 409: the product is already pending. Re-render the list unchanged and say why.
        logger.warning("Shopping item rejected: name=%r status=%d", name, e.response.status_code)
        add_error = error_detail(e, "Could not add the item.")
    except httpx.HTTPError as e:
        logger.error("Failed to create shopping item: name=%r error=%s", name, e)
        return HTMLResponse("", status_code=422)

    status = request.query_params.get("status", "pending")
    list_category_id = request.query_params.get("category_id")
    try:
        items = await api.get("/organizer/shopping", params=_shopping_list_params(status, list_category_id))
    except httpx.HTTPError as e:
        logger.error("Failed to reload shopping items after create: error=%s", e)
        items = []

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": _FREQUENT_LIMIT})
    except httpx.HTTPError as e:
        logger.error("Failed to reload frequent shopping items after create: error=%s", e)
        frequent_items = []

    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}

    list_html = templates.env.get_template("_shopping_list.html").render({
        "items": items,
        "categories_by_id": categories_by_id,
    })
    frequent_html = templates.env.get_template("_shopping_frequent.html").render({
        "frequent_items": frequent_items,
        "oob": True,
    })
    error_html = templates.env.get_template("_shopping_add_error.html").render({"message": add_error})
    return HTMLResponse(list_html + frequent_html + error_html)


@router.post("/{item_id}/bought", response_class=HTMLResponse)
async def mark_bought(item_id: int, request: Request):
    try:
        item = await api.post(f"/organizer/shopping/{item_id}/bought")
    except httpx.HTTPError as e:
        logger.error("Failed to mark shopping item bought: id=%d error=%s", item_id, e)
        return HTMLResponse("", status_code=422)
    return templates.TemplateResponse(request, "_shopping_item.html", {"item": item})


# --- Recurring items ---

@router.post("/recurring/{item_id}/accept", response_class=HTMLResponse)
async def accept_recurring_item(item_id: int, request: Request):
    try:
        await api.post(f"/organizer/recurrence/{item_id}/accept")
    except httpx.HTTPError as e:
        logger.error("Failed to accept recurring item: id=%d error=%s", item_id, e)
        return HTMLResponse("", status_code=422)

    status = request.query_params.get("status", "pending")
    category_id = request.query_params.get("category_id")
    try:
        items = await api.get("/organizer/shopping", params=_shopping_list_params(status, category_id))
    except httpx.HTTPError as e:
        logger.error("Failed to reload shopping items after recurrence accept: error=%s", e)
        items = []

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": _FREQUENT_LIMIT})
    except httpx.HTTPError as e:
        logger.error("Failed to reload frequent shopping items after recurrence accept: error=%s", e)
        frequent_items = []

    try:
        due_recurrences = await api.get("/organizer/recurrence/due")
    except httpx.HTTPError as e:
        logger.error("Failed to reload due recurring items after accept: error=%s", e)
        due_recurrences = []

    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}

    list_html = templates.env.get_template("_shopping_list.html").render({
        "items": items,
        "categories_by_id": categories_by_id,
    })
    frequent_html = templates.env.get_template("_shopping_frequent.html").render({
        "frequent_items": frequent_items,
        "oob": True,
    })
    recurring_html = templates.env.get_template("_shopping_recurring.html").render({
        "due_recurrences": due_recurrences,
        "oob": True,
    })
    return HTMLResponse(list_html + frequent_html + recurring_html)


# --- Wishlist ---

@router.get("/wishlist", response_class=HTMLResponse)
async def wishlist_fragment(request: Request):
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to load wishlist items: error=%s", e)
        items = []
    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories_by_id": categories_by_id})


@router.post("/wishlist", response_class=HTMLResponse)
async def add_wishlist_item(
    request: Request,
    name: Annotated[str, Form()],
    category_id: Annotated[int, Form()],
    estimated_price: Annotated[Optional[str], Form()] = None,
    brand: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "category_id": category_id}
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
    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories_by_id": categories_by_id})


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
    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories_by_id": categories_by_id})


@router.post("/wishlist/{item_id}/promote", response_class=HTMLResponse)
async def promote_wishlist_item(item_id: int, request: Request):
    try:
        await api.post(f"/organizer/wishlist/{item_id}/promote", json={"priority": "want"})
    except httpx.HTTPError as e:
        logger.error("Failed to promote wishlist item: id=%d error=%s", item_id, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to promote item.</p>', status_code=422)

    items = []
    try:
        items = await api.get("/organizer/wishlist", params={"limit": 100})
    except httpx.HTTPError as e:
        logger.error("Failed to reload wishlist items after promote: error=%s", e)
    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}
    return templates.TemplateResponse(request, "_wishlist_list.html", {"items": items, "categories_by_id": categories_by_id})


# --- Categories ---

@router.post("/categories", response_class=HTMLResponse)
async def create_shopping_category(
    request: Request,
    name: Annotated[str, Form()],
):
    try:
        await api.post("/organizer/shopping-categories", json={"name": name})
    except httpx.HTTPError as e:
        logger.error("Failed to create shopping category: name=%r error=%s", name, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create category.</p>', status_code=422)

    categories = await _get_categories()
    return templates.TemplateResponse(request, "_shopping_categories.html", {"categories": categories})


@router.delete("/categories/{category_id}", response_class=HTMLResponse)
async def delete_shopping_category(category_id: int, request: Request):
    try:
        await api.delete(f"/organizer/shopping-categories/{category_id}")
    except httpx.HTTPError as e:
        logger.error("Failed to delete shopping category: id=%d error=%s", category_id, e)
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete category.</p>', status_code=422)

    categories = await _get_categories()
    return templates.TemplateResponse(request, "_shopping_categories.html", {"categories": categories})


# --- Products ---

async def _get_products(q: str | None = None) -> list[dict]:
    params: dict = {"limit": 500}
    if q:
        params["q"] = q
    try:
        return await api.get("/organizer/shopping-products", params=params)
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping products: error=%s", e)
        return []


def _products_html(products: list[dict], categories: list[dict], error: str = "") -> HTMLResponse:
    list_html = templates.env.get_template("_shopping_products.html").render({
        "products": products,
        "categories": categories,
    })
    error_html = templates.env.get_template("_shopping_products_error.html").render({"message": error})
    return HTMLResponse(list_html + error_html)


@router.get("/products", response_class=HTMLResponse)
async def products_fragment(request: Request):
    q = request.query_params.get("q", "").strip()
    return _products_html(await _get_products(q), await _get_categories())


@router.post("/products", response_class=HTMLResponse)
async def create_product(
    name: Annotated[str, Form()],
    category_id: Annotated[int, Form()],
    default_unit: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {"name": name, "category_id": category_id}
    if default_unit:
        payload["default_unit"] = default_unit
    error = ""
    try:
        await api.post("/organizer/shopping-products", json=payload)
    except httpx.HTTPStatusError as e:
        logger.warning("Shopping product rejected: name=%r status=%d", name, e.response.status_code)
        error = error_detail(e, "Could not create the product.")
    except httpx.HTTPError as e:
        logger.error("Failed to create shopping product: name=%r error=%s", name, e)
        error = "Could not create the product."
    return _products_html(await _get_products(), await _get_categories(), error)


@router.post("/products/merge")
async def merge_products(source_id: Annotated[int, Form()], into_id: Annotated[int, Form()]):
    try:
        await api.post(f"/organizer/shopping-products/{source_id}/merge", json={"into_id": into_id})
    except httpx.HTTPStatusError as e:
        logger.warning("Shopping product merge rejected: source=%d into=%d status=%d", source_id, into_id, e.response.status_code)
        return HTMLResponse(error_detail(e, "Could not merge the products."), status_code=e.response.status_code)
    except httpx.HTTPError as e:
        logger.error("Failed to merge shopping products: source=%d into=%d error=%s", source_id, into_id, e)
        return HTMLResponse("Could not merge the products.", status_code=502)
    return HTMLResponse("")


@router.post("/products/{product_id}", response_class=HTMLResponse)
async def update_product(
    product_id: int,
    request: Request,
    name: Annotated[str, Form()],
    category_id: Annotated[int, Form()],
    default_unit: Annotated[Optional[str], Form()] = None,
    default_quantity: Annotated[Optional[str], Form()] = None,
):
    payload = {
        "name": name,
        "category_id": category_id,
        "default_unit": default_unit or None,
        "default_quantity": default_quantity or None,
    }
    error = ""
    try:
        await api.patch(f"/organizer/shopping-products/{product_id}", json=payload)
    except httpx.HTTPStatusError as e:
        logger.warning("Shopping product update rejected: id=%d status=%d", product_id, e.response.status_code)
        error = error_detail(e, "Could not save the product.")
    except httpx.HTTPError as e:
        logger.error("Failed to update shopping product: id=%d error=%s", product_id, e)
        error = "Could not save the product."
    # Re-render the whole list so a rejected rename snaps back to what the backend has.
    return _products_html(await _get_products(), await _get_categories(), error)


@router.delete("/products/{product_id}", response_class=HTMLResponse)
async def delete_product(product_id: int):
    error = ""
    try:
        await api.delete(f"/organizer/shopping-products/{product_id}")
    except httpx.HTTPStatusError as e:
        logger.warning("Shopping product delete rejected: id=%d status=%d", product_id, e.response.status_code)
        error = error_detail(e, "Could not delete the product.")
    except httpx.HTTPError as e:
        logger.error("Failed to delete shopping product: id=%d error=%s", product_id, e)
        error = "Could not delete the product."
    return _products_html(await _get_products(), await _get_categories(), error)
