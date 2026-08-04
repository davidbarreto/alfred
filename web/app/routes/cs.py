from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/cs")

_SUBMISSIONS_PAGE_SIZE = 10
_SUBMISSIONS_LIST_PAGE_SIZE = 20
_PROBLEMS_PREVIEW_SIZE = 10
_PROBLEMS_PAGE_SIZE = 20
_STUDY_PLANS_PAGE_SIZE = 10

_ACTIVITY_RANGE_DAYS = {
    "30": 30,
    "60": 60,
    "90": 90,
    "1y": 365,
    "always": None,
}

_DIFFICULTY_COLOR = {
    "easy": "text-green-600 bg-green-50",
    "medium": "text-amber-600 bg-amber-50",
    "hard": "text-red-600 bg-red-50",
}
_VERDICT_COLOR = {
    "accepted": "text-green-600 bg-green-50",
}
_PLAN_STATUS_COLOR = {
    "active": "text-blue-600 bg-blue-50",
    "completed": "text-green-600 bg-green-50",
    "abandoned": "text-gray-500 bg-gray-50",
    "superseded": "text-gray-500 bg-gray-50",
}


def _pagination(items: list, offset: int, page_size: int) -> tuple[list, bool, bool]:
    has_next = len(items) > page_size
    return items[:page_size], has_next, offset > 0


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
        s["tags"] = [t["name"] for t in problem["tags"]] if problem else []
        s["verdict_color"] = _VERDICT_COLOR.get(s["verdict"], "text-gray-500 bg-gray-50")


def _relative_time(iso_timestamp: str | None) -> str:
    if not iso_timestamp:
        return "never synced"
    then = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - then
    seconds = delta.total_seconds()
    if seconds < 3600:
        return f"{max(1, int(seconds // 60))}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _sync_status_text(platforms: list) -> str:
    parts = []
    for p in platforms:
        if p["code"] not in ("codeforces", "leetcode"):
            continue
        label = p["code"].title() if p["code"] == "codeforces" else "LeetCode"
        parts.append(f"{label} synced {_relative_time(p.get('last_synced_at'))}")
    return " · ".join(parts)


def _by_tag_share(by_tag: list, total_attempted: int, limit: int = 10) -> dict:
    """Share of all problems tried that fall under each tag, not solve rate.

    Problems carry multiple tags, so shares don't sum to 100% -- that's expected,
    it's meant to show which categories are over/under-represented in practice.
    """
    if not total_attempted:
        return {}
    top = sorted(by_tag, key=lambda t: -t["attempted"])[:limit]
    return {t["tag"]: round(t["attempted"] / total_attempted * 100) for t in top}


def _enrich_attempted_problems(problems: list, platform_by_id: dict) -> None:
    for p in problems:
        platform = platform_by_id.get(p["platform_id"])
        p["platform_code"] = platform["code"] if platform else "?"
        p["tag_names"] = [t["name"] for t in p["tags"]]


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    summary = await _safe_get("/cs/stats/summary")
    live_recommendation = await _safe_get("/cs/recommendations/live")
    active_plan = await _safe_get("/cs/study-plans/active/weekly")
    platforms = await _safe_get("/cs/platforms") or []
    platform_by_id = {p["id"]: p for p in platforms}

    raw = await _safe_get("/cs/submissions", {"limit": _SUBMISSIONS_PAGE_SIZE + 1}) or []
    submissions, has_next, has_prev = _pagination(raw, 0, _SUBMISSIONS_PAGE_SIZE)
    await _enrich_submissions(submissions, platform_by_id)

    attempted_raw = await _safe_get("/cs/problems/attempted", {"limit": _PROBLEMS_PREVIEW_SIZE}) or []
    _enrich_attempted_problems(attempted_raw, platform_by_id)

    activity_solved: dict = {}
    activity_attempts: dict = {}
    difficulty_chart: dict = {}
    tag_strength_chart: dict = {}
    language_chart: dict = {}
    if summary:
        activity_solved = {d["date"]: d["solved"] for d in summary["by_day"]}
        activity_attempts = {d["date"]: d["attempts"] for d in summary["by_day"]}
        difficulty_chart = {d["difficulty"]: d["solved"] for d in summary["by_difficulty"]}
        tag_strength_chart = _by_tag_share(summary["by_tag"], summary["total_attempted"])
        language_chart = {l["language"]: l["solved"] for l in summary["by_language"]}

    return templates.TemplateResponse(request, "cs.html", {
        "summary": summary,
        "live_recommendation": live_recommendation,
        "active_plan": active_plan,
        "sync_status_text": _sync_status_text(platforms),
        "submissions": submissions,
        "submissions_offset": 0,
        "submissions_has_next": has_next,
        "submissions_has_prev": has_prev,
        "attempted_problems": attempted_raw,
        "difficulty_color": _DIFFICULTY_COLOR,
        "activity_solved": activity_solved,
        "activity_attempts": activity_attempts,
        "difficulty_chart": difficulty_chart,
        "tag_strength_chart": tag_strength_chart,
        "language_chart": language_chart,
    })


@router.get("/submissions-section", response_class=HTMLResponse)
async def submissions_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    platform_by_id = await _platform_lookup()

    raw = await _safe_get("/cs/submissions", {"limit": _SUBMISSIONS_PAGE_SIZE + 1, "offset": offset}) or []
    submissions, has_next, has_prev = _pagination(raw, offset, _SUBMISSIONS_PAGE_SIZE)
    await _enrich_submissions(submissions, platform_by_id)

    return templates.TemplateResponse(request, "_cs_submissions.html", {
        "submissions": submissions,
        "submissions_offset": offset,
        "submissions_has_next": has_next,
        "submissions_has_prev": has_prev,
    })


def _submission_filters_from_request(request: Request) -> dict:
    filters = {}
    for key in ("platform_id", "verdict", "tag", "q"):
        value = request.query_params.get(key)
        if value:
            filters[key] = value
    return filters


@router.get("/submissions", response_class=HTMLResponse)
async def submissions_page(request: Request):
    filters = _submission_filters_from_request(request)
    platforms = await _safe_get("/cs/platforms") or []
    tags = await _safe_get("/cs/problems/tags") or []

    return templates.TemplateResponse(request, "cs_submissions.html", {
        "platforms": platforms,
        "tags": tags,
        "filters": filters,
    })


@router.get("/submissions-list-section", response_class=HTMLResponse)
async def submissions_list_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    filters = _submission_filters_from_request(request)
    platform_by_id = await _platform_lookup()

    raw = await _safe_get(
        "/cs/submissions", {**filters, "limit": _SUBMISSIONS_LIST_PAGE_SIZE + 1, "offset": offset}
    ) or []
    submissions, has_next, has_prev = _pagination(raw, offset, _SUBMISSIONS_LIST_PAGE_SIZE)
    await _enrich_submissions(submissions, platform_by_id)

    return templates.TemplateResponse(request, "_cs_submissions_list.html", {
        "submissions": submissions,
        "filters": filters,
        "submissions_offset": offset,
        "submissions_has_next": has_next,
        "submissions_has_prev": has_prev,
    })


@router.get("/activity-chart-data")
async def activity_chart_data(request: Request):
    range_key = request.query_params.get("range", "90")
    days = _ACTIVITY_RANGE_DAYS.get(range_key, 90)

    raw = await _safe_get("/cs/stats/activity", {"days": days} if days is not None else {}) or []
    return JSONResponse({
        "solved": {d["date"]: d["solved"] for d in raw},
        "attempts": {d["date"]: d["attempts"] for d in raw},
    })


def _problem_filters_from_request(request: Request) -> dict:
    filters = {}
    for key in ("platform_id", "difficulty", "tag", "status", "q"):
        value = request.query_params.get(key)
        if value:
            filters[key] = value
    return filters


@router.get("/problems", response_class=HTMLResponse)
async def problems_page(request: Request):
    filters = _problem_filters_from_request(request)
    platforms = await _safe_get("/cs/platforms") or []
    tags = await _safe_get("/cs/problems/tags") or []

    return templates.TemplateResponse(request, "cs_problems.html", {
        "platforms": platforms,
        "tags": tags,
        "filters": filters,
        "difficulty_color": _DIFFICULTY_COLOR,
    })


@router.get("/problems-section", response_class=HTMLResponse)
async def problems_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    filters = _problem_filters_from_request(request)
    platform_by_id = await _platform_lookup()

    raw = await _safe_get(
        "/cs/problems/attempted", {**filters, "limit": _PROBLEMS_PAGE_SIZE + 1, "offset": offset}
    ) or []
    problems, has_next, has_prev = _pagination(raw, offset, _PROBLEMS_PAGE_SIZE)
    _enrich_attempted_problems(problems, platform_by_id)

    return templates.TemplateResponse(request, "_cs_problems_list.html", {
        "problems": problems,
        "filters": filters,
        "problems_offset": offset,
        "problems_has_next": has_next,
        "problems_has_prev": has_prev,
        "difficulty_color": _DIFFICULTY_COLOR,
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
async def generate_plan(cadence: str, request: Request):
    if cadence not in ("weekly", "monthly"):
        return JSONResponse({"error": "Unknown cadence."}, status_code=404)
    force = request.query_params.get("force") == "true"
    path = f"/cs/recommendations/plans/{cadence}" + ("?force=true" if force else "")
    try:
        plan = await api.post(path, timeout=60.0)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            detail = exc.response.json().get("detail", {})
            return JSONResponse(
                {
                    "error": detail.get("message", "The current plan still has unfinished items."),
                    "incomplete": True,
                },
                status_code=409,
            )
        return JSONResponse({"error": "Could not generate a study plan."}, status_code=502)
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not generate a study plan."}, status_code=502)
    return JSONResponse(plan)


@router.get("/plans", response_class=HTMLResponse)
async def study_plans_page(request: Request):
    return templates.TemplateResponse(request, "cs_study_plans.html", {})


@router.get("/plans-list-section", response_class=HTMLResponse)
async def study_plans_list_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    raw = await _safe_get("/cs/study-plans", {"limit": _STUDY_PLANS_PAGE_SIZE + 1, "offset": offset}) or []
    plans, has_next, has_prev = _pagination(raw, offset, _STUDY_PLANS_PAGE_SIZE)
    return templates.TemplateResponse(request, "_cs_study_plans_list.html", {
        "plans": plans,
        "plans_offset": offset,
        "plans_has_next": has_next,
        "plans_has_prev": has_prev,
        "plan_status_color": _PLAN_STATUS_COLOR,
    })


@router.post("/plans/items/{item_id}/complete")
async def complete_item(item_id: int):
    try:
        await api.post(f"/cs/study-plans/items/{item_id}/complete")
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not update item."}, status_code=502)
    return JSONResponse({"ok": True})
