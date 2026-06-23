from datetime import date, timedelta
from typing import Annotated, Optional

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

    api_error: str | None = None
    try:
        tasks = await api.get("/organizer/tasks/", params=params)
    except httpx.HTTPStatusError as e:
        tasks = []
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        tasks = []
        api_error = f"Cannot reach backend: {e}"

    return templates.TemplateResponse(request, "tasks.html", {
        "tasks": tasks,
        "active_filter": active_filter,
        "filters": _FILTER_DEFS,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "api_error": api_error,
    })


@router.get("/list", response_class=HTMLResponse)
async def tasks_list_fragment(request: Request):
    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)

    try:
        tasks = await api.get("/organizer/tasks/", params=params)
    except httpx.HTTPError:
        tasks = []

    return templates.TemplateResponse(request, "_tasks_list.html", {
        "tasks": tasks,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.post("/", response_class=HTMLResponse)
async def create_task(
    request: Request,
    title: Annotated[str, Form()],
    priority: Annotated[str, Form()] = "LOW",
    urgency: Annotated[str, Form()] = "NORMAL",
    deadline: Annotated[Optional[str], Form()] = None,
    tags: Annotated[str, Form()] = "",
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    payload: dict = {"title": title, "priority": priority, "urgency": urgency, "tags": tag_list}
    if deadline:
        payload["deadline"] = deadline
    try:
        task = await api.post("/organizer/tasks/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create task.</p>', status_code=422)

    await api.log_command("task.add", {"title": title}, "task", task.get("id"))

    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)
    tasks = []
    try:
        tasks = await api.get("/organizer/tasks/", params=params)
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "tasks": tasks,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.post("/{task_id}/done", response_class=HTMLResponse)
async def mark_task_done(task_id: int, request: Request):
    try:
        task = await api.post(f"/organizer/tasks/{task_id}/complete")
        await api.log_command("task.done", {"task_id": task_id}, "task", task_id)
    except httpx.HTTPError:
        task = {"id": task_id, "title": "—", "status": "DONE", "priority": "LOW",
                "urgency": "NORMAL", "deadline": None, "tags": [], "is_done_today": True}
    return templates.TemplateResponse(request, "_task_row.html", {
        "task": task,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.patch("/{task_id}/doing", response_class=HTMLResponse)
async def mark_task_doing(task_id: int, request: Request):
    try:
        task = await api.patch(f"/organizer/tasks/{task_id}/", json={"status": "DOING"})
        await api.log_command("task.doing", {"task_id": task_id}, "task", task_id)
    except httpx.HTTPError:
        task = {"id": task_id, "title": "—", "status": "DOING", "priority": "LOW",
                "urgency": "NORMAL", "deadline": None, "tags": []}
    return templates.TemplateResponse(request, "_task_row.html", {
        "task": task,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })
