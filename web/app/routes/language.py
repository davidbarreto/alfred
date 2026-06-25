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
        chunks = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "status": "pending_triage", "limit": 1
        })
        triage_counts[track["id"]] = len(chunks)

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
    all_sessions = []
    for track in tracks:
        sessions = await _safe_get("/language/sessions/", {
            "track_id": track["id"], "limit": 500
        })
        all_sessions.extend(sessions)

        chunks_active = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "status": "active", "limit": 1
        })
        chunks_leech = await _safe_get("/language/chunks/", {
            "track_id": track["id"], "is_leech": "true", "limit": 200
        })

        retention = _retention_rate(sessions)

        sessions_by_week: Counter = Counter()
        for s in sessions:
            if s.get("feeds_srs"):
                d = date.fromisoformat(s["created_at"][:10])
                week_start = d - timedelta(days=d.weekday())
                sessions_by_week[week_start.isoformat()] += 1

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
            "sessions_by_week": dict(sessions_by_week),
        })

    heatmap = _build_heatmap(all_sessions, today)

    type_counts = Counter(s["session_type"] for s in all_sessions)
    total_sessions = len(all_sessions)
    total_srs = sum(1 for s in all_sessions if s.get("feeds_srs"))

    return templates.TemplateResponse(request, "language_insights.html", {
        "track_stats": track_stats,
        "heatmap_weeks": heatmap,
        "type_counts": dict(type_counts),
        "total_sessions": total_sessions,
        "total_srs": total_srs,
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
    params: dict = {"track_id": track["id"], "limit": 100}
    active_status = qp.get("status", "active")
    active_type = qp.get("type", "")
    leech_only = qp.get("leech") == "1"
    due_only = qp.get("due") == "1"

    if active_status != "ALL":
        params["status"] = active_status
    if active_type:
        params["chunk_type"] = active_type
    if leech_only:
        params["is_leech"] = "true"
    if due_only:
        params["due_only"] = "true"

    chunks = await _safe_get("/language/chunks/", params)
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
        chunks = await _safe_get("/language/chunks/", {
            "track_id": track_id, "status": status, "limit": 1
        })
        counts[status] = len(chunks)
    return counts
