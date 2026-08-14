from datetime import date, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response
from typing import Annotated, Optional

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/tasks")

_FILTER_DEFS = {
    "all":       {"label": "All",       "status": "ACTIVE"},
    "today":     {"label": "Today",     "status": "TODO"},
    "this_week": {"label": "This week", "status": "TODO"},
    "habits":    {"label": "Habits",    "status": "ACTIVE"},
    "one_off":   {"label": "One-off",   "status": "ACTIVE"},
    "work":      {"label": "Work",      "status": "ACTIVE", "tags": ["work"]},
    "personal":  {"label": "Personal",  "status": "ACTIVE", "tags": ["personal"]},
    "completed": {"label": "Completed", "status": "DONE"},
}


def _build_params(active_filter: str, extra_tags: list[str] | None = None) -> dict:
    today = date.today()
    defn = _FILTER_DEFS.get(active_filter, _FILTER_DEFS["all"])
    params: dict = {"status": defn["status"], "limit": 200}

    if active_filter == "today":
        params["due_today"] = "true"
    elif active_filter == "this_week":
        params["deadline_from"] = today.isoformat()
        params["deadline_to"] = (today + timedelta(days=6)).isoformat()
        params["include_recurring"] = "true"
    elif active_filter in ("habits", "one_off"):
        # Fetch all; filter recurring/non-recurring in the route handler
        params["limit"] = 200

    tags = list(defn.get("tags", []))
    for tag in extra_tags or []:
        if tag not in tags:
            tags.append(tag)
    if tags:
        params["tags"] = tags

    return params


def _tag_toggle_href(active_filter: str, selected_tags: list[str], tag: str) -> str:
    new_tags = [t for t in selected_tags if t != tag] if tag in selected_tags else selected_tags + [tag]
    query = [("filter", active_filter)] + [("tag", t) for t in new_tags]
    return "/tasks?" + urlencode(query)


def _apply_recurrence_filter(tasks: list[dict], active_filter: str) -> list[dict]:
    if active_filter == "habits":
        return [t for t in tasks if t.get("recurrence_rule")]
    if active_filter == "one_off":
        return [t for t in tasks if not t.get("recurrence_rule")]
    return tasks


@router.get("/", response_class=HTMLResponse)
async def tasks_page(request: Request):
    active_filter = request.query_params.get("filter", "all")
    selected_tags = request.query_params.getlist("tag")
    params = _build_params(active_filter, selected_tags)

    try:
        available_tags = await api.get("/organizer/tasks/tags")
    except httpx.HTTPError:
        available_tags = []

    api_error: str | None = None
    try:
        tasks = await api.get("/organizer/tasks", params=params)
        tasks = _apply_recurrence_filter(tasks, active_filter)
    except httpx.HTTPStatusError as e:
        tasks = []
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        tasks = []
        api_error = f"Cannot reach backend: {e}"

    tag_chips = [
        {
            "name": tag,
            "active": tag in selected_tags,
            "href": _tag_toggle_href(active_filter, selected_tags, tag),
        }
        for tag in available_tags
    ]

    return templates.TemplateResponse(request, "tasks.html", {
        "tasks": tasks,
        "active_filter": active_filter,
        "filters": _FILTER_DEFS,
        "tag_chips": tag_chips,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "api_error": api_error,
    })


@router.get("/list", response_class=HTMLResponse)
async def tasks_list_fragment(request: Request):
    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)

    try:
        tasks = await api.get("/organizer/tasks", params=params)
        tasks = _apply_recurrence_filter(tasks, active_filter)
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
    recurrence_rule: Annotated[Optional[str], Form()] = None,
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    payload: dict = {"title": title, "priority": priority, "urgency": urgency, "tags": tag_list}
    if deadline:
        payload["deadline"] = deadline
    if recurrence_rule:
        payload["recurrence_rule"] = recurrence_rule
    try:
        await api.post("/organizer/tasks", json=payload)
    except httpx.HTTPStatusError as exc:
        detail = "Failed to save task."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return Response(detail, status_code=422, media_type="text/plain")
    except httpx.HTTPError:
        return Response("Failed to save task.", status_code=422, media_type="text/plain")

    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)
    tasks = []
    try:
        tasks = await api.get("/organizer/tasks", params=params)
    except httpx.HTTPError:
        pass
    return templates.TemplateResponse(request, "_tasks_list.html", {
        "tasks": tasks,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.patch("/{task_id}", response_class=HTMLResponse)
async def update_task(
    task_id: int,
    request: Request,
    title: Annotated[str, Form()],
    priority: Annotated[str, Form()] = "LOW",
    urgency: Annotated[str, Form()] = "NORMAL",
    deadline: Annotated[Optional[str], Form()] = None,
    tags: Annotated[str, Form()] = "",
    recurrence_rule: Annotated[Optional[str], Form()] = None,
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    payload: dict = {
        "title": title,
        "priority": priority,
        "urgency": urgency,
        "tags": tag_list,
        "deadline": deadline or None,
        "recurrence_rule": recurrence_rule or None,
    }
    try:
        await api.patch(f"/organizer/tasks/{task_id}", json=payload)
    except httpx.HTTPStatusError as exc:
        detail = "Failed to update task."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return Response(detail, status_code=422, media_type="text/plain")
    except httpx.HTTPError:
        return Response("Failed to update task.", status_code=422, media_type="text/plain")

    active_filter = request.query_params.get("filter", "all")
    params = _build_params(active_filter)
    tasks = []
    try:
        tasks = await api.get("/organizer/tasks", params=params)
        tasks = _apply_recurrence_filter(tasks, active_filter)
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
        task = await api.patch(f"/organizer/tasks/{task_id}", json={"status": "DOING"})
    except httpx.HTTPError:
        task = {"id": task_id, "title": "—", "status": "DOING", "priority": "LOW",
                "urgency": "NORMAL", "deadline": None, "tags": []}
    return templates.TemplateResponse(request, "_task_row.html", {
        "task": task,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
    })


@router.post("/{task_id}/snooze", response_class=HTMLResponse)
async def snooze_task(task_id: int, request: Request):
    try:
        await api.post(f"/organizer/tasks/{task_id}/snooze")
        task = await api.get(f"/organizer/tasks/{task_id}")
    except httpx.HTTPError:
        return Response("Failed to snooze task.", status_code=422, media_type="text/plain")
    return templates.TemplateResponse(request, "_task_row.html", {
        "task": task,
        "today": date.today().isoformat(),
        "tomorrow": (date.today() + timedelta(days=1)).isoformat(),
        "just_snoozed": True,
    })


@router.get("/{task_id}/history", response_class=HTMLResponse)
async def task_history(task_id: int, request: Request):
    try:
        task = await api.get(f"/organizer/tasks/{task_id}")
        raw_completions = await api.get(f"/organizer/tasks/{task_id}/completions")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-sm text-gray-400 p-4">Could not load history.</p>')

    completions = [
        {
            "date": c["occurrence_date"],
            "day": date.fromisoformat(c["occurrence_date"]).strftime("%a"),
        }
        for c in raw_completions
    ]
    return templates.TemplateResponse(request, "_task_history.html", {
        "task": task,
        "completions": completions,
    })
