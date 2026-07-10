import asyncio
import json
from collections import Counter, defaultdict
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/languages")

_FLAG = {"fr": "🇫🇷", "ru": "🇷🇺", "es": "🇪🇸", "it": "🇮🇹", "de": "🇩🇪"}
_LEVEL_COLOR = {
    "A1": "bg-gray-100 text-gray-500",
    "A2": "bg-gray-100 text-gray-600",
    "B1": "bg-blue-100 text-blue-700",
    "B2": "bg-blue-100 text-blue-800",
    "C1": "bg-purple-100 text-purple-700",
    "C2": "bg-purple-100 text-purple-800",
}
_SOURCE_LABEL = {
    "pareto_list": "Frequency list",
    "mistake": "Mistake",
    "llm_suggested": "AI suggested",
    "reading": "Reading",
}

_CHUNK_PAGE_SIZE = 50
_GRAMMAR_PAGE_SIZE = 10
_SESSIONS_PAGE_SIZE = 10


def _pagination(items: list, offset: int, page_size: int) -> tuple[list, bool, bool]:
    """Return (page_slice, has_next, has_prev) using the limit+1 trick."""
    has_next = len(items) > page_size
    return items[:page_size], has_next, offset > 0


def _flag(code: str) -> str:
    return _FLAG.get(code.lower(), "🌐")


def _level_color(level: str) -> str:
    return _LEVEL_COLOR.get(level, "bg-gray-100 text-gray-500")


def _ease_color(ease: float) -> str:
    if ease < 2.0:
        return "text-red-600"
    if ease < 2.5:
        return "text-amber-600"
    return "text-green-600"


def _retention_rate(sessions: list) -> int | None:
    srs = [s for s in sessions if s.get("feeds_srs") and s.get("quality_score") is not None]
    if not srs:
        return None
    good = sum(1 for s in srs if s["quality_score"] >= 2.5)
    return round(good / len(srs) * 100)


def _shadowing_score(session: dict) -> float | None:
    feedback = session.get("ai_feedback_json") or {}
    if "score" in feedback:
        return feedback["score"]
    if session.get("quality_score") is not None:
        return session["quality_score"] * 25
    return None


def _build_shadowing_chart(shadowing_sessions: list) -> dict | None:
    """Compact SVG line-chart geometry (oldest→newest) of scores; None if <2 scored attempts."""
    attempts = list(reversed(shadowing_sessions))  # API returns newest-first
    points = []
    for s in attempts:
        score = _shadowing_score(s)
        if score is None:
            continue
        points.append({
            "date": s["created_at"][:10],
            "score": round(score),
            "summary": (s.get("ai_feedback_json") or {}).get("summary") or "",
        })
    if len(points) < 2:
        return None

    width, height, pad = 280, 64, 8
    n = len(points)
    for i, p in enumerate(points):
        p["x"] = round(pad + (i / (n - 1)) * (width - 2 * pad), 1)
        p["y"] = round(pad + (1 - p["score"] / 100) * (height - 2 * pad), 1)
    polyline = " ".join(f"{p['x']},{p['y']}" for p in points)
    return {"width": width, "height": height, "points": points, "polyline": polyline}


def _build_heatmap(sessions: list, today: date) -> list:
    counts: Counter = Counter(
        s["created_at"][:10] for s in sessions if s.get("feeds_srs")
    )
    start = today - timedelta(weeks=12, days=today.weekday())
    prev_month = ""
    weeks = []
    for w in range(13):
        days = []
        month_label = ""
        for d in range(7):
            dt = start + timedelta(weeks=w, days=d)
            iso = dt.isoformat()
            m = dt.strftime("%b")
            if d == 0 and m != prev_month:
                month_label = m
                prev_month = m
            days.append({
                "date": iso,
                "label": dt.strftime("%b %d"),
                "count": counts.get(iso, 0),
                "future": dt > today,
            })
        weeks.append({"days": days, "month_label": month_label})
    return weeks


def _compute_streaks(all_sessions: list, today: date) -> dict:
    srs_days: set[date] = {
        date.fromisoformat(s["created_at"][:10])
        for s in all_sessions if s.get("feeds_srs")
    }
    if not srs_days:
        return {"current": 0, "longest": 0}
    longest = _longest_streak(srs_days)
    yesterday = today - timedelta(days=1)
    anchor = today if today in srs_days else (yesterday if yesterday in srs_days else None)
    if anchor is None:
        return {"current": 0, "longest": longest}
    current = 0
    d = anchor
    while d in srs_days:
        current += 1
        d -= timedelta(days=1)
    return {"current": current, "longest": longest}


def _longest_streak(srs_days: set[date]) -> int:
    if not srs_days:
        return 0
    sorted_days = sorted(srs_days)
    longest = current = 1
    for i in range(1, len(sorted_days)):
        if (sorted_days[i] - sorted_days[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _weekly_stats(all_sessions: list, today: date, n_weeks: int = 8) -> list[dict]:
    """Per-week retention rate and average Gemini score, oldest first."""
    result = []
    for w in range(n_weeks - 1, -1, -1):
        week_start = today - timedelta(weeks=w, days=today.weekday())
        week_end = week_start + timedelta(days=6)

        week_srs = [
            s for s in all_sessions
            if s.get("feeds_srs") and s.get("quality_score") is not None
            and week_start <= date.fromisoformat(s["created_at"][:10]) <= week_end
        ]
        week_shadow = [
            s for s in all_sessions
            if s.get("session_type") == "shadowing" and s.get("quality_score") is not None
            and week_start <= date.fromisoformat(s["created_at"][:10]) <= week_end
        ]

        retention = (
            round(sum(1 for s in week_srs if s["quality_score"] >= 2.5) / len(week_srs) * 100)
            if week_srs else None
        )
        gemini_avg = (
            round(sum(s["quality_score"] for s in week_shadow) / len(week_shadow), 2)
            if week_shadow else None
        )

        result.append({
            "label": week_start.strftime("%b %d"),
            "retention": retention,
            "gemini_avg": gemini_avg,
            "srs_count": len(week_srs),
            "shadow_count": len(week_shadow),
        })
    return result


def _daily_reviews(all_sessions: list, today: date, n_days: int = 14) -> list[dict]:
    result = []
    for d in range(n_days - 1, -1, -1):
        day = today - timedelta(days=d)
        iso = day.isoformat()
        count = sum(1 for s in all_sessions if s.get("feeds_srs") and s["created_at"][:10] == iso)
        result.append({"label": day.strftime("%b %d"), "count": count})
    return result


def _ease_distribution(all_chunks: list) -> list[dict]:
    # FSRS difficulty is 1–10; default for new cards is 5.0 (medium).
    # Buckets are centered so that the unreviewed default lands in "Medium".
    buckets = [
        {"label": "Very Easy", "range": "<2.5", "count": 0, "color": "#22c55e"},
        {"label": "Easy",      "range": "2.5–4.0", "count": 0, "color": "#86efac"},
        {"label": "Medium",    "range": "4.0–6.0", "count": 0, "color": "#fbbf24"},
        {"label": "Hard",      "range": "6.0–8.0", "count": 0, "color": "#f97316"},
        {"label": "Very Hard", "range": ">8.0",    "count": 0, "color": "#ef4444"},
    ]
    for c in all_chunks:
        d = c.get("difficulty", 5.0)
        if d < 2.5:
            buckets[0]["count"] += 1
        elif d < 4.0:
            buckets[1]["count"] += 1
        elif d < 6.0:
            buckets[2]["count"] += 1
        elif d < 8.0:
            buckets[3]["count"] += 1
        else:
            buckets[4]["count"] += 1
    return buckets


def _interval_distribution(all_chunks: list) -> list[dict]:
    buckets = [
        {"label": "New",    "range": "<1d",    "count": 0},
        {"label": "Short",  "range": "1–7d",   "count": 0},
        {"label": "Medium", "range": "7–30d",  "count": 0},
        {"label": "Long",   "range": "30–90d", "count": 0},
        {"label": "Mature", "range": ">90d",   "count": 0},
    ]
    for c in all_chunks:
        s = c.get("stability", 0.0)
        if s < 1:
            buckets[0]["count"] += 1
        elif s < 7:
            buckets[1]["count"] += 1
        elif s < 30:
            buckets[2]["count"] += 1
        elif s < 90:
            buckets[3]["count"] += 1
        else:
            buckets[4]["count"] += 1
    return buckets


async def _safe_get(path: str, params: dict | None = None) -> list | dict:
    try:
        return await api.get(path, params=params or {})
    except httpx.HTTPError:
        return []


# ── Hub ──────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def hub(request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    progress = await _safe_get("/language/sessions/daily-progress")
    progress_by_track = {p["track_id"]: p for p in progress}

    triage_counts: dict[int, int] = {}
    for track in tracks:
        result = await _safe_get("/language/chunks/count", {
            "track_id": track["id"], "status": "pending_triage"
        })
        triage_counts[track["id"]] = result.get("count", 0) if isinstance(result, dict) else 0

    total_triage = sum(triage_counts.values())

    for t in tracks:
        t["flag"] = _flag(t["code"])
        t["level_color"] = _level_color(t["level"])
        p = progress_by_track.get(t["id"])
        t["completed_today"] = p["completed_today"] if p else 0
        t["quota_met"] = p["quota_met"] if p else False
        t["triage_count"] = triage_counts.get(t["id"], 0)

    return templates.TemplateResponse(request, "languages.html", {
        "tracks": tracks,
        "total_triage": total_triage,
    })


# ── Track detail ─────────────────────────────────────────────────────────────

@router.get("/triage", response_class=HTMLResponse)
async def triage_page(request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    active_code = request.query_params.get("lang")

    all_chunks = []
    for track in tracks:
        chunks = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "status": "pending_triage", "limit": 200
        })
        for c in chunks:
            c["track_code"] = track["code"]
            c["track_name"] = track["name"]
            c["flag"] = _flag(track["code"])
            c["source_label"] = _SOURCE_LABEL.get(c.get("frequency_source", ""), c.get("frequency_source") or "—")
        all_chunks.extend(chunks)

    if active_code:
        visible = [c for c in all_chunks if c["track_code"] == active_code]
    else:
        visible = all_chunks

    counts_by_lang = defaultdict(int)
    for c in all_chunks:
        counts_by_lang[c["track_code"]] += 1

    return templates.TemplateResponse(request, "language_triage.html", {
        "chunks": visible,
        "tracks": tracks,
        "active_code": active_code,
        "counts_by_lang": dict(counts_by_lang),
        "total": len(all_chunks),
    })


@router.patch("/grammar-scope/{scope_id}/status", response_class=HTMLResponse)
async def update_scope_status(scope_id: int, request: Request):
    body = await request.json()
    try:
        await api.patch(f"/language/grammar-scope/{scope_id}", json={"status": body.get("status")})
    except httpx.HTTPError:
        pass
    return HTMLResponse("")


@router.post("/triage/{chunk_id}/approve", response_class=HTMLResponse)
async def approve_chunk(chunk_id: int, request: Request):
    try:
        await api.post(f"/language/chunks/{chunk_id}/approve")
    except httpx.HTTPError:
        pass
    return HTMLResponse("")


@router.post("/triage/{chunk_id}/reject", response_class=HTMLResponse)
async def reject_chunk(chunk_id: int, request: Request):
    try:
        await api.delete(f"/language/chunks/{chunk_id}")
    except httpx.HTTPError:
        pass
    return HTMLResponse("")


@router.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    today = date.today()

    track_stats = []
    all_sessions: list = []
    all_active_chunks: list = []

    for track in tracks:
        sessions = await _safe_get("/language/sessions/", {
            "track_id": track["id"], "limit": 500
        })
        all_sessions.extend(sessions)

        active_chunks = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "status": "active", "limit": 500
        })
        all_active_chunks.extend(active_chunks)

        chunks_leech = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "is_leech": "true", "limit": 200
        })

        retention = _retention_rate(sessions)

        track_stats.append({
            "id": track["id"],
            "code": track["code"],
            "name": track["name"],
            "flag": _flag(track["code"]),
            "level": track["level"],
            "level_color": _level_color(track["level"]),
            "active": track["active"],
            "retention": retention,
            "leech_count": len(chunks_leech),
            "active_count": len(active_chunks),
        })

    heatmap = _build_heatmap(all_sessions, today)

    type_counts = Counter(s["session_type"] for s in all_sessions)
    total_sessions = len(all_sessions)
    total_srs = sum(1 for s in all_sessions if s.get("feeds_srs"))

    streaks = _compute_streaks(all_sessions, today)
    weekly_stats = _weekly_stats(all_sessions, today)
    daily_reviews = _daily_reviews(all_sessions, today)
    ease_dist = _ease_distribution(all_active_chunks)
    interval_dist = _interval_distribution(all_active_chunks)

    return templates.TemplateResponse(request, "language_insights.html", {
        "track_stats": track_stats,
        "heatmap_weeks": heatmap,
        "type_counts": dict(type_counts),
        "total_sessions": total_sessions,
        "total_srs": total_srs,
        "streaks": streaks,
        "weekly_stats_json": json.dumps(weekly_stats),
        "daily_reviews_json": json.dumps(daily_reviews),
        "ease_dist_json": json.dumps(ease_dist),
        "interval_dist_json": json.dumps(interval_dist),
    })


@router.get("/{code}/grammar-section", response_class=HTMLResponse)
async def grammar_section(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    offset = max(0, int(request.query_params.get("offset", "0")))
    raw = await _safe_get("/language/grammar-scope/", {
        "track_id": track["id"],
        "limit": _GRAMMAR_PAGE_SIZE + 1,
        "offset": offset,
    })
    scopes, scope_has_next, scope_has_prev = _pagination(raw, offset, _GRAMMAR_PAGE_SIZE)
    return templates.TemplateResponse(request, "_language_grammar_scope.html", {
        "track": track,
        "scopes": scopes,
        "scope_offset": offset,
        "scope_has_next": scope_has_next,
        "scope_has_prev": scope_has_prev,
    })


@router.get("/{code}/sessions-section", response_class=HTMLResponse)
async def sessions_section(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    offset = max(0, int(request.query_params.get("offset", "0")))
    raw = await _safe_get("/language/sessions/", {
        "track_id": track["id"],
        "limit": _SESSIONS_PAGE_SIZE + 1,
        "offset": offset,
    })
    sessions, sessions_has_next, sessions_has_prev = _pagination(raw, offset, _SESSIONS_PAGE_SIZE)
    await _enrich_with_chunk_text(sessions)
    return templates.TemplateResponse(request, "_language_recent_sessions.html", {
        "track": track,
        "recent_sessions": sessions,
        "sessions_offset": offset,
        "sessions_has_next": sessions_has_next,
        "sessions_has_prev": sessions_has_prev,
    })


@router.get("/{code}/review", response_class=HTMLResponse)
async def review_session(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    daily_batch = await _safe_get("/language/chunks/daily-batch", {"track_id": track["id"]})
    due_batch = daily_batch[0] if daily_batch else {"chunks": [], "total_due": 0}
    chunks = due_batch.get("chunks", [])

    progress = await _safe_get("/language/sessions/daily-progress", {"track_id": track["id"]})
    prog = progress[0] if progress else {"completed_today": 0, "quota_met": False, "daily_quota": track["daily_quota"]}

    return templates.TemplateResponse(request, "language_review.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "chunks_json": json.dumps(chunks),
        "total_due": due_batch.get("total_due", 0),
        "completed_today": prog["completed_today"],
        "daily_quota": prog["daily_quota"],
    })


_PRODUCE_TASK_TYPES = ("sentence", "translate")


async def _next_production_task(track_id: int, task_type: str | None = None) -> dict | None:
    """Fetch the next production exercise; None when nothing is due (backend 404)."""
    params: dict = {"track_id": track_id}
    if task_type in _PRODUCE_TASK_TYPES:
        params["task_type"] = task_type
    try:
        return await api.get("/language/production/next-task", params=params)
    except httpx.HTTPError:
        return None


@router.get("/{code}/produce", response_class=HTMLResponse)
async def produce_session(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    task_type = request.query_params.get("type")
    task = await _next_production_task(track["id"], task_type)

    return templates.TemplateResponse(request, "language_produce.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "task_json": json.dumps(task),
        "total_due": task["total_due"] if task else 0,
        "active_type": task_type if task_type in _PRODUCE_TASK_TYPES else "",
    })


@router.get("/{code}/produce/next")
async def produce_next(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return JSONResponse({"error": "Track not found."}, status_code=404)

    task = await _next_production_task(track["id"], request.query_params.get("type"))
    if task is None:
        return JSONResponse({"done": True})
    return JSONResponse({"done": False, "task": task})


@router.post("/{code}/produce/attempt")
async def produce_attempt(code: str, request: Request):
    body = await request.json()
    try:
        result = await api.post("/language/production/attempts", json={
            "track_id": body["track_id"],
            "chunk_id": body["chunk_id"],
            "task_type": body["task_type"],
            "prompt_text": body["prompt_text"],
            "response_text": body["response_text"],
        })
    except (KeyError, httpx.HTTPError):
        return JSONResponse({"error": "Could not grade your answer. Please try again."}, status_code=502)
    return JSONResponse(result)


@router.get("/{code}/pronounce")
async def pronounce(code: str, text: str):
    try:
        audio, content_type = await api.get_bytes("/language/chunks/pronunciation", {"text": text, "lang": code})
    except httpx.HTTPError:
        return Response(status_code=502)
    return Response(content=audio, media_type=content_type)


@router.get("/{code}/sessions/{session_id}/audio")
async def session_audio(code: str, session_id: int):
    try:
        audio, content_type = await api.get_bytes(f"/language/sessions/{session_id}/audio")
    except httpx.HTTPError:
        return Response(status_code=502)
    return Response(content=audio, media_type=content_type)


@router.post("/{code}/chunks/{chunk_id}/shadow")
async def submit_shadowing(code: str, chunk_id: int, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return JSONResponse({"error": "Track not found."}, status_code=404)

    form = await request.form()
    upload = form.get("audio")
    if upload is None:
        return JSONResponse({"error": "No audio provided."}, status_code=400)
    audio_bytes = await upload.read()

    try:
        result = await api.post_multipart(
            "/language/sessions/shadowing/audio",
            data={"track_id": track["id"], "chunk_id": chunk_id},
            files={"audio": (upload.filename or "recording.webm", audio_bytes, upload.content_type or "audio/webm")},
        )
    except httpx.HTTPError:
        return JSONResponse({"error": "Could not analyze recording."}, status_code=502)
    return JSONResponse(result)


@router.post("/{code}/review/score")
async def score_review(code: str, request: Request):
    body = await request.json()
    try:
        await api.post("/language/sessions/srs-review", json={
            "track_id": body["track_id"],
            "chunk_id": body["chunk_id"],
            "quality_score": body["quality_score"],
        })
    except httpx.HTTPError:
        pass
    return {}


@router.get("/{code}", response_class=HTMLResponse)
async def track_detail(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    scopes_all, sessions_all, due_batch = await _fetch_track_data(track["id"])

    chunk_counts = await _count_chunks_by_status(track["id"])
    progress = await _safe_get("/language/sessions/daily-progress", {"track_id": track["id"]})
    prog = progress[0] if progress else {"completed_today": 0, "quota_met": False, "daily_quota": track["daily_quota"]}

    retention = _retention_rate(sessions_all)

    mastery_list = await _safe_get("/language/production/mastery", {"track_id": track["id"]})
    mastery = mastery_list[0] if mastery_list else None

    scopes_page, scope_has_next, scope_has_prev = _pagination(scopes_all, 0, _GRAMMAR_PAGE_SIZE)
    sessions_page, sessions_has_next, sessions_has_prev = _pagination(sessions_all, 0, _SESSIONS_PAGE_SIZE)
    await _enrich_with_chunk_text(sessions_page)

    return templates.TemplateResponse(request, "language_track.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "level_color": _level_color(track["level"]),
        "scopes": scopes_page,
        "scope_total": len(scopes_all),
        "scope_offset": 0,
        "scope_has_next": scope_has_next,
        "scope_has_prev": False,
        "recent_sessions": sessions_page,
        "sessions_offset": 0,
        "sessions_has_next": sessions_has_next,
        "sessions_has_prev": False,
        "due_batch": due_batch,
        "chunk_counts": chunk_counts,
        "progress": prog,
        "retention": retention,
        "mastery": mastery,
    })


_DIFFICULTY_BUCKETS: dict[str, tuple[float, float]] = {
    "very_easy": (0.0, 2.5),
    "easy":      (2.5, 4.0),
    "medium":    (4.0, 6.0),
    "hard":      (6.0, 8.0),
    "very_hard": (8.0, 10.0),
}


@router.get("/{code}/chunks", response_class=HTMLResponse)
async def chunk_browser(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    qp = request.query_params
    active_status = qp.get("status", "active")
    active_type = qp.get("type", "")
    leech_only = qp.get("leech") == "1"
    due_only = qp.get("due") == "1"
    active_cefr = qp.get("cefr", "").strip().upper()
    active_difficulty = qp.get("difficulty", "").strip()
    page = max(1, int(qp.get("page", "1")))

    filter_params: dict = {"track_id": track["id"]}
    if active_status != "ALL":
        filter_params["status"] = active_status
    if active_type:
        filter_params["chunk_type"] = active_type
    if leech_only:
        filter_params["is_leech"] = "true"
    if due_only:
        filter_params["due_only"] = "true"
    if active_cefr:
        filter_params["cefr_level"] = active_cefr
    if active_difficulty and active_difficulty in _DIFFICULTY_BUCKETS:
        dmin, dmax = _DIFFICULTY_BUCKETS[active_difficulty]
        filter_params["difficulty_min"] = dmin
        filter_params["difficulty_max"] = dmax

    count_result = await _safe_get("/language/chunks/count", filter_params)
    total_count = count_result.get("count", 0) if isinstance(count_result, dict) else 0
    total_pages = max(1, (total_count + _CHUNK_PAGE_SIZE - 1) // _CHUNK_PAGE_SIZE)
    page = min(page, total_pages)

    chunks = await _safe_get("/language/chunks/", {
        **filter_params,
        "limit": _CHUNK_PAGE_SIZE,
        "offset": (page - 1) * _CHUNK_PAGE_SIZE,
    })
    for c in chunks:
        c["ease_color"] = _ease_color(c.get("difficulty", 5.0))

    return templates.TemplateResponse(request, "language_chunks.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "chunks": chunks,
        "active_status": active_status,
        "active_type": active_type,
        "leech_only": leech_only,
        "due_only": due_only,
        "active_cefr": active_cefr,
        "active_difficulty": active_difficulty,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "page_size": _CHUNK_PAGE_SIZE,
    })


@router.get("/{code}/chunks/{chunk_id}", response_class=HTMLResponse)
async def chunk_detail(code: str, chunk_id: int, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    chunk = await _safe_get(f"/language/chunks/{chunk_id}")
    if not chunk or isinstance(chunk, list):
        return HTMLResponse("<p>Chunk not found.</p>", status_code=404)

    sessions = await _safe_get("/language/sessions/", {
        "chunk_id": chunk_id, "limit": 50
    })

    shadowing = [s for s in sessions if s["session_type"] == "shadowing"]
    srs_reviews = [s for s in sessions if s["session_type"] == "srs_review"]
    production = [s for s in sessions if s["session_type"] == "production"]

    chunk["ease_color"] = _ease_color(chunk.get("difficulty", 5.0))
    chunk["source_label"] = _SOURCE_LABEL.get(chunk.get("frequency_source", ""), chunk.get("frequency_source") or "—")

    return templates.TemplateResponse(request, "language_chunk_detail.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "chunk": chunk,
        "shadowing_sessions": shadowing,
        "srs_sessions": srs_reviews,
        "production_sessions": production,
        "shadowing_chart": _build_shadowing_chart(shadowing),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_track_data(track_id: int):
    scopes = await _safe_get("/language/grammar-scope/", {"track_id": track_id, "limit": 500})
    sessions = await _safe_get("/language/sessions/", {"track_id": track_id, "limit": _SESSIONS_PAGE_SIZE + 1})
    daily_batch = await _safe_get("/language/chunks/daily-batch", {"track_id": track_id})
    due_batch = daily_batch[0] if daily_batch else {"chunks": [], "total_due": 0}
    return scopes, sessions, due_batch


async def _enrich_with_chunk_text(sessions: list) -> None:
    chunk_ids = list({s["chunk_id"] for s in sessions if s.get("chunk_id")})
    if not chunk_ids:
        return
    results = await asyncio.gather(*[_safe_get(f"/language/chunks/{cid}") for cid in chunk_ids])
    chunk_text_map = {
        c["id"]: c.get("text", "")
        for c in results
        if isinstance(c, dict) and c.get("id")
    }
    for session in sessions:
        if session.get("chunk_id"):
            session["chunk_text"] = chunk_text_map.get(session["chunk_id"])


async def _count_chunks_by_status(track_id: int) -> dict:
    counts = {}
    for status in ("active", "pending_triage", "suspended"):
        result = await _safe_get("/language/chunks/count", {
            "track_id": track_id, "status": status
        })
        counts[status] = result.get("count", 0) if isinstance(result, dict) else 0
    return counts
