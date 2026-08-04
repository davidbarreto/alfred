import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping/insights")

_FREQUENT_CHART_SIZE = 10


async def _get_categories() -> list[dict]:
    try:
        return await api.get("/organizer/shopping-categories")
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping categories: error=%s", e)
        return []


@router.get("/", response_class=HTMLResponse)
async def shopping_insights_page(request: Request):
    frequent_items, by_category, by_month, priority_split, by_store = [], [], [], [], []

    try:
        frequent_items = await api.get("/organizer/shopping/frequent", params={"limit": 15})
    except httpx.HTTPError as e:
        logger.error("Failed to load frequent shopping items: error=%s", e)

    try:
        by_category = await api.get("/organizer/shopping/insights/by-category")
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping purchases by category: error=%s", e)

    try:
        by_month = await api.get("/organizer/shopping/insights/by-month", params={"months": 6})
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping purchases by month: error=%s", e)

    try:
        priority_split = await api.get("/organizer/shopping/insights/priority-split")
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping priority split: error=%s", e)

    try:
        by_store = await api.get("/organizer/shopping/insights/by-store")
    except httpx.HTTPError as e:
        logger.error("Failed to load shopping purchases by store: error=%s", e)

    categories_by_id = {c["id"]: c["name"] for c in await _get_categories()}

    frequent_chart = {i["name"]: i["purchase_count"] for i in frequent_items[:_FREQUENT_CHART_SIZE]}
    by_category_chart = {
        categories_by_id.get(r["category_id"], f"#{r['category_id']}"): r["purchase_count"] for r in by_category
    }
    by_month_chart = {r["month"]: r["purchase_count"] for r in by_month}
    priority_chart = {r["priority"]: r["item_count"] for r in priority_split}
    by_store_chart = {r["store"]: r["purchase_count"] for r in by_store}

    return templates.TemplateResponse(request, "shopping_insights.html", {
        "frequent_items": frequent_items,
        "frequent_chart": frequent_chart,
        "by_category_chart": by_category_chart,
        "by_month_chart": by_month_chart,
        "priority_chart": priority_chart,
        "by_store_chart": by_store_chart,
    })
