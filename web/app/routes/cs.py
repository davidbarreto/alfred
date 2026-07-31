import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/cs")

_SUBMISSIONS_PAGE_SIZE = 20

_DIFFICULTY_COLOR = {
    "easy": "text-green-600 bg-green-50",
    "medium": "text-amber-600 bg-amber-50",
    "hard": "text-red-600 bg-red-50",
}
_VERDICT_COLOR = {
    "accepted": "text-green-600 bg-green-50",
}


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _SUBMISSIONS_PAGE_SIZE
    return items[:_SUBMISSIONS_PAGE_SIZE], has_next, offset > 0


async def _safe_get(path: str, params: dict | None = None):
    try:
        return await api.get(path, params=params or {})
    except httpx.HTTPError:
        return None


async def _platform_lookup() -> dict[int, dict]:
    platforms = await _safe_get("/cs/platforms") or []
    return {p["id"]: p for p in platforms}


async def _enrich_submissions(submissions: list, platform_by_id: dict) -> None:
    problem_ids = list({s["problem_id"] for s in submissions})
    problems = {}
    for pid in problem_ids:
        problem = await _safe_get(f"/cs/problems/{pid}")
        if problem:
            problems[pid] = problem
    for s in submissions:
        platform = platform_by_id.get(s["platform_id"])
        s["platform_code"] = platform["code"] if platform else "?"
        problem = problems.get(s["problem_id"])
        s["problem_name"] = problem["name"] if problem else f"#{s['problem_id']}"
        s["problem_url"] = problem["url"] if problem else None
        s["verdict_color"] = _VERDICT_COLOR.get(s["verdict"], "text-gray-500 bg-gray-50")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = await _safe_get("/cs/stats/summary")
    live_recommendation = await _safe_get("/cs/recommendations/live")
    weekly_plan = await _safe_get("/cs/study-plans/active/weekly")
    platforms = await _safe_get("/cs/platforms") or []
    platform_by_id = {p["id"]: p for p in platforms}

    raw = await _safe_get("/cs/submissions", {"limit": _SUBMISSIONS_PAGE_SIZE + 1}) or []
    submissions, has_next, has_prev = _pagination(raw, 0)
    await _enrich_submissions(submissions, platform_by_id)

    for p in platforms:
        p["difficulty_color"] = _DIFFICULTY_COLOR

    return templates.TemplateResponse(request, "cs.html", {
        "summary": summary,
        "live_recommendation": live_recommendation,
        "weekly_plan": weekly_plan,
        "platforms": platforms,
        "submissions": submissions,
        "submissions_offset": 0,
        "submissions_has_next": has_next,
        "submissions_has_prev": has_prev,
        "difficulty_color": _DIFFICULTY_COLOR,
    })


@router.get("/submissions-section", response_class=HTMLResponse)
async def submissions_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    platform_by_id = await _platform_lookup()

    raw = await _safe_get("/cs/submissions", {"limit": _SUBMISSIONS_PAGE_SIZE + 1, "offset": offset}) or []
    submissions, has_next, has_prev = _pagination(raw, offset)
    await _enrich_submissions(submissions, platform_by_id)

    return templates.TemplateResponse(request, "_cs_submissions.html", {
        "submissions": submissions,
        "submissions_offset": offset,
        "submissions_has_next": has_next,
        "submissions_has_prev": has_prev,
    })


@router.post("/sync/{platform_code}")
async def trigger_sync(platform_code: str):
    if platform_code not in ("codeforces", "leetcode"):
        return JSONResponse({"error": "Unknown platform."}, status_code=404)
    try:
        result = await api.post(f"/cs/platforms/{platform_code}/sync", timeout=60.0)
    except httpx.HTTPStatusError as exc:
        detail = "Sync failed."
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        return JSONResponse({"error": detail}, status_code=exc.response.status_code)
    except httpx.HTTPError:
        return JSONResponse({"error": "Sync failed."}, status_code=502)
    return JSONResponse(result)


@router.post("/plans/{cadence}/generate")
async def generate_plan(cadence: str):
    if cadence not in ("weekly", "monthly"):
        return JSONResponse({"error": "Unknown cadence."}, status_code=404)
    try:
        plan = await api.post(f"/cs/recommendations/plans/{cadence}", timeout=60.0)
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not generate a study plan."}, status_code=502)
    return JSONResponse(plan)


@router.post("/plans/items/{item_id}/complete")
async def complete_item(item_id: int):
    try:
        await api.post(f"/cs/study-plans/items/{item_id}/complete")
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not update item."}, status_code=502)
    return JSONResponse({"ok": True})
