import json
from collections import Counter, defaultdict
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

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
    buckets = [
        {"label": "Very Easy", "range": "<2.5", "count": 0, "color": "#22c55e"},
        {"label": "Easy",      "range": "2.5–3.5", "count": 0, "color": "#86efac"},
        {"label": "Medium",    "range": "3.5–5.0", "count": 0, "color": "#fbbf24"},
        {"label": "Hard",      "range": "5.0–6.5", "count": 0, "color": "#f97316"},
        {"label": "Very Hard", "range": ">6.5",  "count": 0, "color": "#ef4444"},
    ]
    for c in all_chunks:
        d = c.get("difficulty", 5.0)
        if d < 2.5:
            buckets[0]["count"] += 1
        elif d < 3.5:
            buckets[1]["count"] += 1
        elif d < 5.0:
            buckets[2]["count"] += 1
        elif d < 6.5:
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


@router.get("/{code}", response_class=HTMLResponse)
async def track_detail(code: str, request: Request):
    tracks = await _safe_get("/language/tracks/", {"active_only": "false"})
    track = next((t for t in tracks if t["code"] == code), None)
    if not track:
        return HTMLResponse("<p>Track not found.</p>", status_code=404)

    scopes, sessions, due_batch = await _fetch_track_data(track["id"])

    chunk_counts = await _count_chunks_by_status(track["id"])
    progress = await _safe_get("/language/sessions/daily-progress", {"track_id": track["id"]})
    prog = progress[0] if progress else {"completed_today": 0, "quota_met": False, "daily_quota": track["daily_quota"]}

    retention = _retention_rate(sessions)

    return templates.TemplateResponse(request, "language_track.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "level_color": _level_color(track["level"]),
        "scopes": scopes,
        "recent_sessions": sessions[:10],
        "due_batch": due_batch,
        "chunk_counts": chunk_counts,
        "progress": prog,
        "retention": retention,
    })


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

    chunk["ease_color"] = _ease_color(chunk.get("difficulty", 5.0))
    chunk["source_label"] = _SOURCE_LABEL.get(chunk.get("frequency_source", ""), chunk.get("frequency_source") or "—")

    return templates.TemplateResponse(request, "language_chunk_detail.html", {
        "track": track,
        "flag": _flag(track["code"]),
        "chunk": chunk,
        "shadowing_sessions": shadowing,
        "srs_sessions": srs_reviews,
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_track_data(track_id: int):
    scopes = await _safe_get("/language/grammar-scope/", {"track_id": track_id})
    sessions = await _safe_get("/language/sessions/", {"track_id": track_id, "limit": 50})
    daily_batch = await _safe_get("/language/chunks/daily-batch", {"track_id": track_id})
    due_batch = daily_batch[0] if daily_batch else {"chunks": [], "total_due": 0}
    return scopes, sessions, due_batch


async def _count_chunks_by_status(track_id: int) -> dict:
    counts = {}
    for status in ("active", "pending_triage", "suspended"):
        result = await _safe_get("/language/chunks/count", {
            "track_id": track_id, "status": status
        })
        counts[status] = result.get("count", 0) if isinstance(result, dict) else 0
    return counts
