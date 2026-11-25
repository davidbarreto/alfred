from datetime import datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/overload")


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        detail = exc.response.json().get("detail")
    except ValueError:
        detail = None
    return detail if isinstance(detail, str) else "Invalid value. Please check the numbers and try again."


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
