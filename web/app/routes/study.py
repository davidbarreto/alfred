import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/study")

_HISTORY_PAGE_SIZE = 10
_PLAN_ACTIONS = ("activate", "complete", "abandon")

_PRIORITY_COLOR = {
    "high": "text-red-600 bg-red-50",
    "medium": "text-amber-600 bg-amber-50",
    "low": "text-gray-500 bg-gray-50",
}
_STATUS_COLOR = {
    "completed": "text-green-600 bg-green-50",
    "abandoned": "text-gray-500 bg-gray-50",
}


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _HISTORY_PAGE_SIZE
    return items[:_HISTORY_PAGE_SIZE], has_next, offset > 0


def _error_detail(exc: httpx.HTTPStatusError, fallback: str) -> str:
    try:
        detail = exc.response.json().get("detail")
    except ValueError:
        return fallback
    return detail if isinstance(detail, str) else fallback


@router.get("", response_class=HTMLResponse)
async def study_page(request: Request):
    try:
        overview = await api.get("/study/plans/overview")
    except httpx.HTTPError:
        overview = None
    return templates.TemplateResponse(request, "study.html", {
        "overview": overview,
        "priority_color": _PRIORITY_COLOR,
    })


@router.get("/history-section", response_class=HTMLResponse)
async def history_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    try:
        raw = await api.get("/study/plans", params={"closed": "true", "limit": _HISTORY_PAGE_SIZE + 1, "offset": offset})
    except httpx.HTTPError:
        raw = []
    plans, has_next, has_prev = _pagination(raw or [], offset)
    return templates.TemplateResponse(request, "_study_history.html", {
        "plans": plans,
        "history_offset": offset,
        "history_has_next": has_next,
        "history_has_prev": has_prev,
        "status_color": _STATUS_COLOR,
    })


@router.post("/plans/generate")
async def generate_plan():
    try:
        plan = await api.post("/study/plans/generate", timeout=60.0)
    except httpx.HTTPStatusError as exc:
        return JSONResponse({"error": _error_detail(exc, "Could not generate a study plan.")}, status_code=502)
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not generate a study plan."}, status_code=502)
    return JSONResponse(plan)


@router.post("/plans/{plan_id}/{action}")
async def plan_action(plan_id: int, action: str):
    if action not in _PLAN_ACTIONS:
        return JSONResponse({"error": "Unknown action."}, status_code=404)
    try:
        plan = await api.post(f"/study/plans/{plan_id}/{action}")
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            {"error": _error_detail(exc, "Could not update the plan.")}, status_code=exc.response.status_code
        )
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not update the plan."}, status_code=502)
    return JSONResponse(plan)


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: int):
    try:
        await api.delete(f"/study/plans/{plan_id}")
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not delete the plan."}, status_code=502)
    return JSONResponse({"ok": True})


@router.post("/items/{item_id}/complete")
async def complete_item(item_id: int):
    try:
        await api.post(f"/study/plans/items/{item_id}/complete")
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not update item."}, status_code=502)
    return JSONResponse({"ok": True})
