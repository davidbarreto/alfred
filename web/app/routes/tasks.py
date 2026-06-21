from datetime import date, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/tasks")

_FILTER_DEFS = {
    "all":       {"label": "All",       "status": "ALL"},
    "today":     {"label": "Today",     "status": "TODO"},
    "this_week": {"label": "This week", "status": "TODO"},
    "work":      {"label": "Work",      "status": "ALL", "tags": ["work"]},
    "personal":  {"label": "Personal",  "status": "ALL", "tags": ["personal"]},
    "completed": {"label": "Completed", "status": "DONE"},
}


def _build_params(active_filter: str) -> dict:
    today = date.today()
    defn = _FILTER_DEFS.get(active_filter, _FILTER_DEFS["all"])
    params: dict = {"status": defn["status"], "limit": 100}

    if active_filter == "today":
        params["deadline_from"] = today.isoformat()
        params["deadline_to"] = today.isoformat()
    elif active_filter == "this_week":
        params["deadline_from"] = today.isoformat()
        params["deadline_to"] = (today + timedelta(days=6)).isoformat()

    if "tags" in defn:
        params["tags"] = defn["tags"]

    return params


@router.get("/", response_class=HTMLResponse)
async def tasks_page(request: Request):
    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)

    try:
        tasks = await api.get("/organizer/tasks", params=params)
    except httpx.HTTPError:
        tasks = []

    return templates.TemplateResponse(request, "tasks.html", {
        "tasks": tasks,
        "active_filter": active_filter,
        "filters": _FILTER_DEFS,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.get("/list", response_class=HTMLResponse)
async def tasks_list_fragment(request: Request):
    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)

    try:
        tasks = await api.get("/organizer/tasks", params=params)
    except httpx.HTTPError:
        tasks = []

    return templates.TemplateResponse(request, "_tasks_list.html", {
        "tasks": tasks,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.post("/{task_id}/done", response_class=HTMLResponse)
async def mark_task_done(task_id: int, request: Request):
    try:
        task = await api.patch(f"/organizer/tasks/{task_id}", json={"status": "DONE"})
    except httpx.HTTPError:
        task = {"id": task_id, "title": "—", "status": "DONE", "priority": "LOW",
                "urgency": "NORMAL", "deadline": None, "tags": []}
    return templates.TemplateResponse(request, "_task_row.html", {
        "task": task,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })
