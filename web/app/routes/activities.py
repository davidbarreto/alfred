from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.timezone import local_today
from app.templates_config import templates

router = APIRouter(prefix="/activities")

_STATS_WEEKS = 12
_CONTEXTS = ("computer", "phone", "home", "out", "anywhere")


def _days_since(last_done_at: str | None, today: date) -> int | None:
    if not last_done_at:
        return None
    return max(0, (today - date.fromisoformat(last_done_at[:10])).days)


def _bar_heights(weeks: list[dict]) -> list[int]:
    """Bar heights as percentages of the busiest week (a non-empty week never rounds to nothing)."""
    peak = max((w["count"] for w in weeks), default=0)
    return [max(6, round(100 * w["count"] / peak)) if w["count"] else 0 for w in weeks]


@router.get("", response_class=HTMLResponse)
async def activities_page(request: Request):
    show_archived = request.query_params.get("archived") == "1"
    activities = await safe_get("/organizer/activities", params={"include_archived": "true" if show_archived else "false"})
    stats = await safe_get("/organizer/activities/stats", params={"weeks": _STATS_WEEKS})
    today = local_today()
    cards = [
        {**a, "days_since": _days_since(a.get("last_done_at"), today)} for a in (activities or [])
    ]
    weeks = (stats or {}).get("weeks", [])
    return templates.TemplateResponse(request, "activities.html", {
        "available": activities is not None,
        "cards": cards,
        "show_archived": show_archived,
        "stats": stats,
        "week_bars": list(zip(weeks, _bar_heights(weeks))),
        "contexts": _CONTEXTS,
    })


@router.post("")
async def create_activity(request: Request):
    return await forward(api.post("/organizer/activities", json=await request.json()), "Could not add the activity.")


@router.patch("/{activity_id}")
async def update_activity(activity_id: int, request: Request):
    return await forward(
        api.patch(f"/organizer/activities/{activity_id}", json=await request.json()), "Could not update the activity."
    )


@router.post("/{activity_id}/log")
async def log_activity(activity_id: int, request: Request):
    return await forward(
        api.post(f"/organizer/activities/{activity_id}/logs", json=await request.json()), "Could not log the activity."
    )


@router.post("/{activity_id}/{action}")
async def archive_activity(activity_id: int, action: str):
    if action not in ("archive", "unarchive"):
        return JSONResponse({"error": "Unknown action."}, status_code=404)
    return await forward(
        api.post(f"/organizer/activities/{activity_id}/{action}"), f"Could not {action} the activity."
    )
