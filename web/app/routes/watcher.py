from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/watcher")


async def _render_list(request: Request) -> HTMLResponse:
    monitors, executions = [], []
    try:
        monitors = await api.get("/watcher/configs", params={"limit": 200})
    except httpx.HTTPError:
        pass
    try:
        executions = await api.get("/watcher/executions", params={"limit": 200})
    except httpx.HTTPError:
        pass

    latest_by_monitor: dict[int, dict] = {}
    for execution in executions:
        latest_by_monitor.setdefault(execution["config_id"], execution)

    return templates.TemplateResponse(request, "_watcher_list.html", {
        "monitors": monitors,
        "latest_by_monitor": latest_by_monitor,
    })


@router.get("/", response_class=HTMLResponse)
async def watcher_page(request: Request):
    monitors, executions, alerts, errors = [], [], [], []

    try:
        monitors = await api.get("/watcher/configs", params={"limit": 200})
    except httpx.HTTPError:
        errors.append("monitors")

    try:
        executions = await api.get("/watcher/executions", params={"limit": 200})
    except httpx.HTTPError:
        errors.append("executions")

    try:
        alerts = await api.get("/watcher/alerts", params={"limit": 20})
    except httpx.HTTPError:
        errors.append("alerts")

    latest_by_monitor: dict[int, dict] = {}
    for execution in executions:
        latest_by_monitor.setdefault(execution["config_id"], execution)

    status_counts: dict[str, int] = defaultdict(int)
    time_counts: dict[str, int] = defaultdict(int)
    for execution in executions:
        status_counts[execution["status"]] += 1
        time_counts[execution["created_at"][:10]] += 1

    today = datetime.now(timezone.utc).date().isoformat()
    executions_today = time_counts.get(today, 0)
    pending_alerts = [a for a in alerts if a["status"] == "pending"]

    status_chart = {
        label: status_counts[key]
        for key, label in (("found", "Found"), ("not_found", "Not found"), ("error", "Error"))
        if status_counts.get(key)
    }

    return templates.TemplateResponse(request, "watcher.html", {
        "monitors": monitors,
        "latest_by_monitor": latest_by_monitor,
        "alerts": alerts,
        "pending_alerts_count": len(pending_alerts),
        "enabled_count": sum(1 for m in monitors if m["enabled"]),
        "executions_today": executions_today,
        "status_chart": status_chart,
        "time_chart": dict(sorted(time_counts.items())),
        "errors": errors,
    })


@router.post("/", response_class=HTMLResponse)
async def create_monitor(
    request: Request,
    name: Annotated[str, Form()],
    type: Annotated[str, Form()],
    url: Annotated[str, Form()],
    target: Annotated[str, Form()],
    description: Annotated[Optional[str], Form()] = None,
    enabled: Annotated[Optional[str], Form()] = None,
    selector: Annotated[Optional[str], Form()] = None,
    json_path: Annotated[Optional[str], Form()] = None,
    case_sensitive: Annotated[Optional[str], Form()] = None,
    timeout: Annotated[int, Form()] = 10,
    page_size: Annotated[Optional[int], Form()] = None,
    max_pages: Annotated[Optional[int], Form()] = None,
    request_delay: Annotated[Optional[int], Form()] = None,
    wait_selector: Annotated[Optional[str], Form()] = None,
):
    payload: dict = {
        "name": name,
        "type": type,
        "url": url,
        "target": target,
        "enabled": enabled == "on",
        "case_sensitive": case_sensitive == "on",
        "timeout": timeout,
    }
    if description:
        payload["description"] = description
    if selector:
        payload["selector"] = selector
    if json_path:
        payload["json_path"] = json_path
    if page_size is not None:
        payload["page_size"] = page_size
    if max_pages is not None:
        payload["max_pages"] = max_pages
    if request_delay is not None:
        payload["request_delay"] = request_delay
    if wait_selector:
        payload["wait_selector"] = wait_selector

    try:
        await api.post("/watcher/configs", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to create monitor.</p>', status_code=422)

    return await _render_list(request)


@router.delete("/{monitor_id}", response_class=HTMLResponse)
async def delete_monitor(monitor_id: int, request: Request):
    try:
        await api.delete(f"/watcher/configs/{monitor_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to delete monitor.</p>', status_code=422)

    return await _render_list(request)


@router.patch("/{monitor_id}/toggle", response_class=HTMLResponse)
async def toggle_monitor(monitor_id: int, request: Request, enabled: Annotated[str, Form()]):
    try:
        await api.patch(f"/watcher/configs/{monitor_id}", json={"enabled": enabled == "true"})
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to update monitor.</p>', status_code=422)

    return await _render_list(request)


@router.post("/{monitor_id}/run", response_class=HTMLResponse)
async def run_monitor(monitor_id: int, request: Request):
    try:
        await api.post(f"/watcher/configs/{monitor_id}/run")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to run monitor.</p>', status_code=422)

    return await _render_list(request)


@router.post("/run", response_class=HTMLResponse)
async def run_all_monitors(request: Request):
    try:
        await api.post("/watcher/configs/run")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm px-1">Failed to run monitors.</p>', status_code=422)

    return await _render_list(request)


@router.get("/{monitor_id}/executions", response_class=HTMLResponse)
async def monitor_executions(monitor_id: int, request: Request):
    executions = []
    try:
        executions = await api.get(f"/watcher/configs/{monitor_id}/executions", params={"limit": 20})
    except httpx.HTTPError:
        pass

    return templates.TemplateResponse(request, "_watcher_executions.html", {"executions": executions})
