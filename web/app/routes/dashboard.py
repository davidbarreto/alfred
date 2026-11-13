import asyncio
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.shared import dashboard as cards
from app.shared.forward import safe_get
from app.shared.timezone import local_now, local_today
from app.templates_config import templates

router = APIRouter()

_TASK_SCAN_LIMIT = 200


async def _optional(path: str, params: dict | None = None):
    """GET that yields None on failure, so one broken module never blanks the dashboard."""
    return await safe_get(path, params=params)


async def _metric_cards() -> list[dict] | None:
    series = await _optional("/metrics/series")
    if series is None:
        return None
    picked = cards.pick_series(series)
    dailies = await asyncio.gather(*[
        _optional(f"/metrics/series/{quote(s['name'], safe='')}/daily", {"days": cards.SPARK_DAYS}) for s in picked
    ])
    today = local_today()
    return [cards.metric_card(s, d, today) for s, d in zip(picked, dailies)]


async def _trip_card() -> dict | None:
    trips = await _optional("/travel/trips", {"status": "current", "limit": 5})
    if not trips:
        return None
    nearest = min(trips, key=lambda t: t["start_date"])
    detail = await _optional(f"/travel/trips/{nearest['id']}")
    return cards.trip_card(trips, detail, local_today())


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    now = local_now()
    today = now.date()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    briefing_kind = cards.briefing_type(now)

    (tasks, shopping_items, events, spending, saved_plans, budgets, contacts, study, briefing_history, metrics,
     trip, language_tracks, language_progress) = await asyncio.gather(
        _optional("/organizer/tasks", {"status": "TODO", "limit": _TASK_SCAN_LIMIT}),
        _optional("/organizer/shopping", {"status": "pending", "limit": 8}),
        _optional("/organizer/calendar-events", {"start_from": today_start, "start_to": today_end, "limit": 10}),
        _optional("/finance/transactions/report", {"period": "this month"}),
        _optional("/planning/saved", {"from": today.isoformat(), "to": today.isoformat()}),
        _optional("/finance/budgets/status"),
        _optional("/organizer/contacts", {"has_birthday": "true", "limit": 1000}),
        _optional("/study/plans/overview"),
        _optional("/briefing/history", {"type": briefing_kind, "limit": 1}),
        _metric_cards(),
        _trip_card(),
        _optional("/language/tracks"),
        _optional("/language/sessions/daily-progress"),
    )

    errors = [name for name, value in (("tasks", tasks), ("shopping", shopping_items), ("events", events),
                                       ("spending", spending)) if value is None]
    open_tasks = tasks or []
    latest_briefing = (briefing_history or [None])[0]
    if briefing_kind == "evening" and (latest_briefing or {}).get("date") != today.isoformat():
        # The digest has not been generated tonight (yet): keep showing the morning briefing.
        briefing_kind = "morning"
        latest_briefing = ((await _optional("/briefing/history", {"type": "morning", "limit": 1})) or [None])[0]

    return templates.TemplateResponse(request, "dashboard.html", {
        "tasks": open_tasks[:8],
        "task_count": len(open_tasks),
        "alerts": cards.task_alerts(open_tasks, now),
        "shopping_items": shopping_items or [],
        "events": events or [],
        "spending": spending,
        "plan": cards.plan_card(saved_plans, today, now.strftime("%H:%M")),
        "trip": trip,
        "metrics": metrics or [],
        "budgets": cards.budget_rows(budgets),
        "birthdays": cards.upcoming_birthdays(contacts, today),
        "study": cards.study_card(study),
        "language": cards.language_card(language_tracks, language_progress),
        "briefing": latest_briefing,
        "briefing_kind": briefing_kind,
        "today": today.isoformat(),
        "tomorrow": (today + timedelta(days=1)).isoformat(),
        "errors": errors,
    })

