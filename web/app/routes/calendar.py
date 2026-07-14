import calendar as cal_lib
from datetime import date, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/calendar")


def _month_range(year: int, month: int) -> tuple[str, str]:
    first = date(year, month, 1)
    last_day = cal_lib.monthrange(year, month)[1]
    last = date(year, month, last_day)
    return (
        datetime(first.year, first.month, first.day).isoformat(),
        datetime(last.year, last.month, last.day, 23, 59, 59).isoformat(),
    )


@router.get("/", response_class=HTMLResponse)
async def calendar_page(request: Request):
    today = date.today()
    year = int(request.query_params.get("year", today.year))
    month = int(request.query_params.get("month", today.month))
    start, end = _month_range(year, month)

    api_error: str | None = None
    try:
        events = await api.get("/organizer/calendar-events", params={
            "start_from": start,
            "start_to": end,
            "limit": 200,
        })
    except httpx.HTTPStatusError as e:
        events = []
        api_error = f"API error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.HTTPError as e:
        events = []
        api_error = f"Cannot reach backend: {e}"

    weeks = cal_lib.monthcalendar(year, month)
    month_name = date(year, month, 1).strftime("%B %Y")

    # Group events by date string for quick lookup in template
    events_by_date: dict[str, list] = {}
    for ev in events:
        ev_date = ev["start_datetime"][:10]
        events_by_date.setdefault(ev_date, []).append(ev)
    for day_events in events_by_date.values():
        day_events.sort(key=lambda e: (not e["all_day"], e["start_datetime"]))

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    return templates.TemplateResponse(request, "calendar.html", {
        "api_error": api_error,
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


@router.get("/day/{date_str}", response_class=HTMLResponse)
async def calendar_day(date_str: str, request: Request):
    try:
        day = date.fromisoformat(date_str)
    except ValueError:
        return HTMLResponse('<p class="text-sm text-gray-400 p-4">Invalid date.</p>')

    start = datetime(day.year, day.month, day.day).isoformat()
    end = datetime(day.year, day.month, day.day, 23, 59, 59).isoformat()

    try:
        events = await api.get("/organizer/calendar-events", params={
            "start_from": start,
            "start_to": end,
            "limit": 200,
        })
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-sm text-gray-400 p-4">Could not load events.</p>')

    events.sort(key=lambda e: (not e["all_day"], e["start_datetime"]))

    return templates.TemplateResponse(request, "_calendar_day.html", {
        "day": day,
        "day_str": date_str,
        "events": events,
    })


def _event_payload(
    title: str, start_date: str, start_time: str, end_time: str, location: str, all_day: str
) -> dict:
    is_all_day = bool(all_day)
    if is_all_day:
        start_iso = f"{start_date}T00:00:00"
        end_iso = f"{start_date}T23:59:59"
    else:
        start_iso = f"{start_date}T{start_time}:00"
        end_iso = f"{start_date}T{end_time}:00"

    return {
        "title": title,
        "start_datetime": start_iso,
        "end_datetime": end_iso,
        "all_day": is_all_day,
        "location": location or None,
    }


@router.post("/", response_class=HTMLResponse)
async def create_event(
    request: Request,
    title: Annotated[str, Form()],
    start_date: Annotated[str, Form()],
    start_time: Annotated[str, Form()] = "09:00",
    end_time: Annotated[str, Form()] = "10:00",
    location: Annotated[str, Form()] = "",
    all_day: Annotated[str, Form()] = "",
):
    payload = _event_payload(title, start_date, start_time, end_time, location, all_day)
    try:
        event = await api.post("/organizer/calendar-events", json=payload)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", "Failed to create event.")
        except Exception:
            detail = "Failed to create event."
        return HTMLResponse(detail, status_code=422)
    except httpx.HTTPError:
        return HTMLResponse("Failed to create event.", status_code=422)

    await api.log_command("event.add", {"title": title}, "event", event.get("id"))
    return HTMLResponse("", status_code=204)


@router.patch("/{event_id}", response_class=HTMLResponse)
async def update_event(
    event_id: int,
    request: Request,
    title: Annotated[str, Form()],
    start_date: Annotated[str, Form()],
    start_time: Annotated[str, Form()] = "09:00",
    end_time: Annotated[str, Form()] = "10:00",
    location: Annotated[str, Form()] = "",
    all_day: Annotated[str, Form()] = "",
):
    payload = _event_payload(title, start_date, start_time, end_time, location, all_day)
    try:
        event = await api.patch(f"/organizer/calendar-events/{event_id}", json=payload)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", "Failed to update event.")
        except Exception:
            detail = "Failed to update event."
        return HTMLResponse(detail, status_code=422)
    except httpx.HTTPError:
        return HTMLResponse("Failed to update event.", status_code=422)

    await api.log_command("event.update", {"title": title}, "event", event.get("id"))
    return HTMLResponse("", status_code=204)
