import calendar as cal_lib
from datetime import date, datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/calendar")


def _month_range(year: int, month: int) -> tuple[str, str]:
    first = date(year, month, 1)
    last_day = cal_lib.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return (
        datetime(first.year, first.month, first.day, tzinfo=timezone.utc).isoformat(),
        datetime(last.year, last.month, last.day, 23, 59, 59, tzinfo=timezone.utc).isoformat(),
    )


@router.get("/", response_class=HTMLResponse)
async def calendar_page(request: Request):
    today = date.today()
    year = int(request.query_params.get("year", today.year))
    month = int(request.query_params.get("month", today.month))
    start, end = _month_range(year, month)

    try:
        events = await api.get("/organizer/calendar-events", params={
            "start_from": start,
            "start_to": end,
            "limit": 200,
        })
    except httpx.HTTPError:
        events = []

    weeks = cal_lib.monthcalendar(year, month)
    month_name = date(year, month, 1).strftime("%B %Y")

    # Group events by date string for quick lookup in template
    events_by_date: dict[str, list] = {}
    for ev in events:
        ev_date = ev["start_datetime"][:10]
        events_by_date.setdefault(ev_date, []).append(ev)

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return templates.TemplateResponse(request, "calendar.html", {
        "events": events,
        "events_by_date": events_by_date,
        "weeks": weeks,
        "year": year,
        "month": month,
        "month_name": month_name,
        "today": today.isoformat(),
        "prev_year": prev_year,
        "prev_month": prev_month,
        "next_year": next_year,
        "next_month": next_month,
    })
