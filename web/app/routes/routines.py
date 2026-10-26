
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.shared.forward import forward, safe_get
from app.shared.timezone import local_now
from app.templates_config import templates

router = APIRouter(prefix="/routines")

_CONTEXTS = ("computer", "phone", "home", "out", "anywhere")
_UPCOMING_EVENTS = 200
_NOTE_OPTIONS = 500


def _clock(value: str | None) -> str:
    return (value or "")[:5]


def _offset_label(anchor: str, offset: int) -> str:
    """'2 h before the start', '25 min after the end', 'at the start'."""
    if offset == 0:
        return f"at the {anchor}"
    minutes = abs(offset)
    hours, rest = divmod(minutes, 60)
    amount = " ".join(part for part in (f"{hours} h" if hours else "", f"{rest} min" if rest else "") if part)
    return f"{amount} {'before' if offset < 0 else 'after'} the {anchor}"


def _timing_label(step: dict) -> str:
    if step.get("anchor"):
        return _offset_label(step["anchor"], step["offset_minutes"])
    return f"{_clock(step.get('window_start'))}–{_clock(step.get('window_end'))}"


def _describe(routine: dict, event_titles: dict[int, str]) -> dict:
    steps = [{**s, "timing_label": _timing_label(s)} for s in routine.get("steps", [])]
    return {
        **routine,
        "scheduled": bool(routine.get("recurrence_rule")),
        "steps": steps,
        "events": [{"id": i, "title": event_titles.get(i, f"Event #{i}")} for i in routine.get("event_ids", [])],
    }


@router.get("", response_class=HTMLResponse)
async def routines_page(request: Request):
    routines = await safe_get("/organizer/routines")
    upcoming = await safe_get(
        "/organizer/calendar-events",
        params={"start_from": local_now().replace(tzinfo=None, microsecond=0).isoformat(), "limit": _UPCOMING_EVENTS},
        default=[],
    )
    notes = await safe_get("/organizer/notes", params={"limit": _NOTE_OPTIONS}, default=[])
    event_titles: dict[int, str] = {}
    for event in upcoming:
        event_titles.setdefault(event["id"], event["title"])
    return templates.TemplateResponse(request, "routines.html", {
        "available": routines is not None,
        "routines": [_describe(r, event_titles) for r in (routines or [])],
        "event_options": list(event_titles.items()),
        "note_options": [(n["id"], n["title"]) for n in notes],
        "contexts": _CONTEXTS,
    })


@router.post("")
async def create_routine(request: Request):
    return await forward(api.post("/organizer/routines", json=await request.json()), "Could not create the routine.")


@router.patch("/steps/{step_id}")
async def update_step(step_id: int, request: Request):
    return await forward(
        api.patch(f"/organizer/routines/steps/{step_id}", json=await request.json()), "Could not update the step."
    )


@router.delete("/steps/{step_id}")
async def delete_step(step_id: int):
    return await forward(_delete(f"/organizer/routines/steps/{step_id}"), "Could not delete the step.")


@router.delete("/events/{event_id}")
async def detach_event(event_id: int):
    return await forward(_delete(f"/organizer/routines/events/{event_id}"), "Could not detach the event.")


@router.patch("/{routine_id}")
async def update_routine(routine_id: int, request: Request):
    return await forward(
        api.patch(f"/organizer/routines/{routine_id}", json=await request.json()), "Could not update the routine."
    )


@router.delete("/{routine_id}")
async def delete_routine(routine_id: int):
    return await forward(_delete(f"/organizer/routines/{routine_id}"), "Could not delete the routine.")


@router.post("/{routine_id}/steps")
async def add_step(routine_id: int, request: Request):
    return await forward(
        api.post(f"/organizer/routines/{routine_id}/steps", json=await request.json()), "Could not add the step."
    )


@router.post("/{routine_id}/events/{event_id}")
async def attach_event(routine_id: int, event_id: int):
    return await forward(
        api.post(f"/organizer/routines/{routine_id}/events/{event_id}"), "Could not attach the event."
    )


async def _delete(path: str) -> dict:
    await api.delete(path)
    return {"deleted": True}
