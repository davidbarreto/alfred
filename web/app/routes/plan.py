from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/plan")

_KIND_ICONS = {
    "event": "ti-calendar-event",
    "task": "ti-checklist",
    "study_item": "ti-brain",
    "activity": "ti-mood-smile",
    "routine_step": "ti-repeat",
    "routine_block": "ti-repeat",
    "meal": "ti-tools-kitchen-2",
    "break": "ti-coffee",
    "other": "ti-dots",
}


def _parse_date(raw: str | None) -> date:
    try:
        return date.fromisoformat(raw) if raw else local_today()
    except ValueError:
        return local_today()


def _clock(iso: str) -> str:
    """HH:MM as written in the stored ISO string (stored in the display zone with its offset)."""
    return iso[11:16]


def _week_days(day: date) -> list[date]:
    monday = day - timedelta(days=day.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


@router.get("", response_class=HTMLResponse)
async def plan_page(request: Request):
    day = _parse_date(request.query_params.get("date"))
    week = _week_days(day)
    saved = await safe_get("/planning/saved", params={"from": week[0].isoformat(), "to": week[-1].isoformat()})
    history = await safe_get("/planning/saved/history", params={"date": day.isoformat()}, default=[])
    settings = await safe_get("/planning/settings")
    by_date = {p["plan_date"]: p for p in (saved or [])}
    active = by_date.get(day.isoformat())
    plan = _pick_version(history, request.query_params.get("version")) or active
    items = [
        {**item, "start_clock": _clock(item["start"]), "end_clock": _clock(item["end"]), "icon": _KIND_ICONS.get(item["kind"], "ti-dots")}
        for item in (plan["items"] if plan else [])
    ]
    return templates.TemplateResponse(request, "plan.html", {
        "available": saved is not None,
        "day": day,
        "today": local_today(),
        "prev_day": (day - timedelta(days=1)).isoformat(),
        "next_day": (day + timedelta(days=1)).isoformat(),
        "week": [{"date": d, "has_plan": d.isoformat() in by_date} for d in week],
        "plan": plan,
        "active_plan": active,
        "items": items,
        "history": history,
        "settings": settings,
    })


def _pick_version(history: list[dict], raw: str | None) -> dict | None:
    """The requested version of the day, or None to fall back to the active one."""
    try:
        wanted = int(raw) if raw else None
    except ValueError:
        return None
    return next((p for p in history if p["version"] == wanted), None)


@router.post("/saved/{plan_id}/archive")
async def archive_plan(plan_id: int):
    return await forward(api.post(f"/planning/saved/{plan_id}/archive"), "Could not archive this version.")


@router.post("/saved/{plan_id}/restore")
async def restore_plan(plan_id: int):
    return await forward(api.post(f"/planning/saved/{plan_id}/restore"), "Could not restore this version.")


@router.delete("/saved/{plan_id}")
async def delete_plan(plan_id: int):
    return await forward(api.delete(f"/planning/saved/{plan_id}"), "Could not delete this version.")


@router.put("/settings")
async def update_settings(request: Request):
    return await forward(api.put("/planning/settings", json=await request.json()), "Could not save the planning settings.")
