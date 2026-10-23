from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/overload")

# (field, label, unit, hint) grouped for the settings form.
_SETTINGS_GROUPS = [
    ("When am I overloaded?", [
        ("overload_overdue_threshold", "Overdue tasks", "tasks", "Overloaded at this many overdue tasks…"),
        ("overload_urgent_threshold", "Urgent tasks", "tasks", "…or this many urgent tasks. Elevated from half."),
    ]),
    ("Reminders while overloaded", [
        ("overload_max_listed", "Tasks per message", "tasks", "Extra tasks rotate into later messages."),
        ("overload_urgent_interval_hours", "Urgent re-remind every", "hours", "Never faster than the normal cadence."),
    ]),
    ("Escalate overdue tasks to Urgent after", [
        ("overdue_grace_hours_high", "High priority", "hours overdue", ""),
        ("overdue_grace_hours_medium", "Medium priority", "hours overdue", ""),
        ("overdue_grace_hours_low", "Low priority", "hours overdue", ""),
    ]),
    ("Escalate undated tasks to Urgent after", [
        ("undated_escalation_days_high", "High priority", "days old", ""),
        ("undated_escalation_days_medium", "Medium priority", "days old", ""),
        ("undated_escalation_days_low", "Low priority", "days old", ""),
    ]),
    ("Catch-up plan", [
        ("catchup_tasks_per_day", "Spread: tasks per day", "tasks", "At most this many due on one day."),
        ("catchup_stale_days", "Stale after", "days overdue", "Non-high tasks overdue this long may be dropped."),
        ("catchup_missed_habit_threshold", "Missed habit after", "misses this week", ""),
    ]),
    ("Urgency reset", [
        ("urgency_reset_days", "Push deadlines / snooze by", "days", ""),
    ]),
]
_SETTING_FIELDS = [field for _, rows in _SETTINGS_GROUPS for field, *_ in rows]


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        detail = exc.response.json().get("detail")
    except ValueError:
        detail = None
    return detail if isinstance(detail, str) else "Invalid value. Please check the numbers and try again."


def _render_settings(request: Request, values: dict, saved: bool = False, error: str | None = None):
    return templates.TemplateResponse(request, "_overload_settings.html", {
        "groups": _SETTINGS_GROUPS,
        "values": values,
        "saved": saved,
        "error": error,
    })


@router.get("/banner", response_class=HTMLResponse)
async def overload_banner(request: Request):
    try:
        status = await api.get("/core/overload/status")
    except httpx.HTTPError:
        return HTMLResponse("")
    return templates.TemplateResponse(request, "_overload_banner.html", {"status": status})


@router.post("/reset", response_class=HTMLResponse)
async def overload_reset():
    try:
        await api.post("/core/urgency-reset")
    except httpx.HTTPError:
        return Response("Failed to reset urgency.", status_code=422, media_type="text/plain")
    # Reload so the page (task list included) and the banner reflect the reset.
    return Response(status_code=200, headers={"HX-Refresh": "true"})


@router.get("/settings", response_class=HTMLResponse)
async def overload_settings(request: Request):
    try:
        values = await api.get("/core/reminder-settings")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-sm text-[#E24B4A]">Could not load reminder settings.</p>')
    return _render_settings(request, values)


@router.post("/settings", response_class=HTMLResponse)
async def save_overload_settings(request: Request):
    form = await request.form()
    payload: dict[str, int] = {}
    for field in _SETTING_FIELDS:
        raw = str(form.get(field, "")).strip()
        if raw:
            try:
                payload[field] = int(raw)
            except ValueError:
                values = await api.get("/core/reminder-settings")
                return _render_settings(request, values, error=f"{field.replace('_', ' ').capitalize()} must be a whole number.")
    try:
        values = await api.put("/core/reminder-settings", json=payload)
    except httpx.HTTPStatusError as exc:
        current = await api.get("/core/reminder-settings")
        return _render_settings(request, current, error=_error_detail(exc))
    return _render_settings(request, values, saved=True)


def _day(iso: str | None) -> str:
    return datetime.fromisoformat(iso).strftime("%a %d %b") if iso else ""


def _render_catchup(request: Request, data: dict, result: str | None = None, error: str | None = None):
    for suggestion in data["suggestions"]:
        for move in suggestion["moves"]:
            move["from_day"] = _day(move["old_deadline"])
            move["to_day"] = _day(move["new_deadline"])
    return templates.TemplateResponse(request, "_catchup_panel.html", {
        "plan": data,
        "result": result,
        "error": error,
    })


@router.get("/catchup", response_class=HTMLResponse)
async def catchup_panel(request: Request):
    try:
        data = await api.get("/core/catchup")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-sm text-[#E24B4A]">Could not load the catch-up plan.</p>')
    return _render_catchup(request, data)


@router.post("/catchup/apply", response_class=HTMLResponse)
async def apply_catchup(request: Request):
    form = await request.form()
    kind = str(form.get("kind", ""))
    payload: dict = {"kind": kind}
    if kind == "drop":
        try:
            payload["task_ids"] = [int(value) for value in form.getlist("task_ids")]
        except ValueError:
            payload["task_ids"] = []
        if not payload["task_ids"]:
            data = await api.get("/core/catchup")
            return _render_catchup(request, data, error="Select at least one task to drop.")

    try:
        outcome = await api.post("/core/catchup/apply", json=payload)
    except httpx.HTTPStatusError as exc:
        data = await api.get("/core/catchup")
        return _render_catchup(request, data, error=_error_detail(exc))

    data = await api.get("/core/catchup")
    verb = "Moved" if kind == "spread" else "Dropped"
    message = f"{verb} {outcome['applied']} task(s)."
    if outcome["skipped"]:
        message += f" {outcome['skipped']} no longer qualified and were left alone."
    response = _render_catchup(request, data, result=message)
    response.headers["HX-Trigger"] = "catchup-applied"
    return response
