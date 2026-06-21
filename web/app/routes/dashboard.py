from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    today_start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = datetime.now(tz=timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    tasks, shopping_items, events, spending = None, None, None, None
    errors = []

    try:
        tasks = await api.get("/organizer/tasks", params={
            "status": "TODO",
            "deadline_to": today_end,
            "limit": 8,
        })
    except httpx.HTTPError:
        errors.append("tasks")

    try:
        shopping_items = await api.get("/organizer/shopping", params={"status": "pending", "limit": 8})
    except httpx.HTTPError:
        errors.append("shopping")

    try:
        events = await api.get("/organizer/calendar-events", params={
            "start_from": today_start,
            "start_to": today_end,
            "limit": 10,
        })
    except httpx.HTTPError:
        errors.append("events")

    try:
        spending = await api.get("/finance/transactions/report", params={"period": "this month"})
    except httpx.HTTPError:
        errors.append("spending")

    return templates.TemplateResponse(request, "dashboard.html", {
        "tasks": tasks or [],
        "shopping_items": shopping_items or [],
        "events": events or [],
        "spending": spending,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "errors": errors,
    })
