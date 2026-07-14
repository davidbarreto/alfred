from collections import Counter, defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/insights")

_PAGE_SIZE = 20
_LLM_CALLS_PREVIEW_SIZE = 5
_LLM_CALL_OPTIONS_LIMIT = 500
_PROVIDER_CALLS_PREVIEW_SIZE = 5
_PROVIDER_CALL_OPTIONS_LIMIT = 500


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    """Return (page_slice, has_next, has_prev) using the limit+1 trick."""
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


_REMINDER_KIND_PATHS = {"task": "/organizer/tasks", "event": "/organizer/calendar-events"}
_REMINDER_KIND_LABELS = {"task": "Task", "event": "Event", "shopping": "Shopping list"}


async def _describe_reminder(item: dict) -> None:
    """Resolve a `reminder:{kind}:{entity_id}:{date}` dedup marker to a readable label."""
    parts = item["key"].split(":", 3)
    if len(parts) != 4:
        return
    _, kind, entity_id, reminded_date = parts
    label = _REMINDER_KIND_LABELS.get(kind, kind.title())

    if kind == "shopping":
        item["display_text"] = f"{label}: pending items reminder"
    else:
        title = f"#{entity_id}"
        path = _REMINDER_KIND_PATHS.get(kind)
        if path:
            try:
                entity = await api.get(f"{path}/{entity_id}")
                title = entity.get("title", title)
            except httpx.HTTPError:
                title = f"#{entity_id} (deleted)"
        item["display_text"] = f"{label}: {title}"
    item["display_meta"] = f"reminded {reminded_date}"


async def _resolve_working_memory(items: list[dict]) -> list[dict]:
    for item in items:
        if item["key"].startswith("reminder:"):
            await _describe_reminder(item)
    return items


def _filter_and_sort_working_memory(raw: list[dict], show_expired: bool) -> tuple[list[dict], int]:
    """Sort by expiry (soonest/null first); optionally drop expired entries. Returns (items, expired_count)."""
    today_str = date.today().isoformat()
    wm_sorted = sorted(raw, key=lambda w: (w.get("expires_at") or ""))
    expired_count = sum(1 for w in wm_sorted if w.get("expires_at") and w["expires_at"][:10] < today_str)
    if not show_expired:
        wm_sorted = [w for w in wm_sorted if not (w.get("expires_at") and w["expires_at"][:10] < today_str)]
    return wm_sorted, expired_count


def _parse_show_expired(request: Request) -> bool:
    return request.query_params.get("show_expired", "").lower() == "true"


@router.get("/memories-section", response_class=HTMLResponse)
async def memories_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    category = request.query_params.get("category", "").strip()
    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    if category:
        params["category"] = category
    try:
        raw = await api.get("/core/memories", params=params)
    except httpx.HTTPError:
        raw = []
    memories, memories_has_next, memories_has_prev = _pagination(raw, offset)
    return templates.TemplateResponse(request, "_insights_memories.html", {
        "memories": memories,
        "memories_offset": offset,
        "memories_has_next": memories_has_next,
        "memories_has_prev": memories_has_prev,
        "memories_category": category,
    })


@router.delete("/memories/{memory_id}", response_class=HTMLResponse)
async def delete_memory(memory_id: int, request: Request):
    try:
        await api.delete(f"/core/memories/{memory_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete memory.</p>', status_code=422)

    category = request.query_params.get("category", "").strip()
    params: dict = {"limit": _PAGE_SIZE + 1, "offset": 0}
    if category:
        params["category"] = category
    try:
        raw = await api.get("/core/memories", params=params)
    except httpx.HTTPError:
        raw = []
    memories, memories_has_next, memories_has_prev = _pagination(raw, 0)
    return templates.TemplateResponse(request, "_insights_memories.html", {
        "memories": memories,
        "memories_offset": 0,
        "memories_has_next": memories_has_next,
        "memories_has_prev": False,
        "memories_category": category,
    })


@router.get("/working-memory-section", response_class=HTMLResponse)
async def working_memory_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    show_expired = _parse_show_expired(request)
    try:
        raw = await api.get("/core/working-memory", params={"active_only": "false", "limit": 200})
    except httpx.HTTPError:
        raw = []
    wm_filtered, wm_expired_count = _filter_and_sort_working_memory(raw, show_expired)
    working_memories, wm_has_next, wm_has_prev = _pagination(wm_filtered[offset:], offset)
    working_memories = await _resolve_working_memory(working_memories)
    return templates.TemplateResponse(request, "_working_memory_list.html", {
        "working_memories": working_memories,
        "wm_offset": offset,
        "wm_has_next": wm_has_next,
        "wm_has_prev": wm_has_prev,
        "wm_show_expired": show_expired,
        "wm_expired_count": wm_expired_count,
        "now": date.today(),
    })


@router.delete("/working-memory/{item_id}", response_class=HTMLResponse)
async def delete_working_memory(item_id: int, request: Request):
    show_expired = _parse_show_expired(request)
    try:
        await api.delete(f"/core/working-memory/{item_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete entry.</p>', status_code=422)

    try:
        raw = await api.get("/core/working-memory", params={"active_only": "false", "limit": 200})
    except httpx.HTTPError:
        raw = []

    wm_filtered, wm_expired_count = _filter_and_sort_working_memory(raw, show_expired)
    working_memories, wm_has_next, wm_has_prev = _pagination(wm_filtered, 0)
    working_memories = await _resolve_working_memory(working_memories)
    return templates.TemplateResponse(request, "_working_memory_list.html", {
        "working_memories": working_memories,
        "wm_offset": 0,
        "wm_has_next": wm_has_next,
        "wm_has_prev": False,
        "wm_show_expired": show_expired,
        "wm_expired_count": wm_expired_count,
        "now": date.today(),
    })


def _expected_30d(rule: str) -> int:
    """Expected completions in 30 days for a given RRULE."""
    if "FREQ=DAILY" in rule:
        return 30
    if "FREQ=WEEKLY" in rule:
        for part in rule.split(";"):
            if part.startswith("BYDAY="):
                return len([d for d in part[len("BYDAY="):].split(",") if d.strip()]) * 4
        return 4
    if "FREQ=MONTHLY" in rule:
        return 1
    return 0


def _build_heatmap(completions_by_date: Counter, today: date) -> list:
    """Build a 13-week × 7-day grid for the completion heatmap."""
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
                "count": completions_by_date.get(iso, 0),
                "future": dt > today,
            })
        weeks.append({"days": days, "month_label": month_label})
    return weeks


@router.get("/", response_class=HTMLResponse)
async def insights_page(request: Request):
    memories_raw, working_memories_raw, llm_calls, provider_calls, cmd_executions = [], [], [], [], []
    all_tasks, task_history = [], []

    for path, params, target in [
        ("/core/memories", {"limit": 200}, "memories"),
        ("/core/working-memory", {"active_only": "false", "limit": 200}, "working_memories"),
        ("/integration/llm-calls", {"limit": 200}, "llm_calls"),
        ("/integration/provider-calls", {"limit": 200}, "provider_calls"),
        ("/core/command-executions", {"limit": 200}, "cmd_executions"),
        ("/organizer/tasks", {"status": "ALL", "limit": 200}, "tasks"),
        ("/organizer/tasks/history", {"days": 90}, "task_history"),
    ]:
        try:
            result = await api.get(path, params=params)
            if target == "memories":          memories_raw = result
            elif target == "working_memories": working_memories_raw = result
            elif target == "llm_calls":       llm_calls = result
            elif target == "provider_calls":  provider_calls = result
            elif target == "cmd_executions":  cmd_executions = result
            elif target == "tasks":           all_tasks = result
            elif target == "task_history":    task_history = result
        except httpx.HTTPError:
            pass

    # ── Task & habit metrics ──────────────────────────────────────
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    cutoff_30d = (today - timedelta(days=30)).isoformat()

    active_task_ids = {t["id"] for t in all_tasks}
    active_history = [c for c in task_history if c["task_id"] in active_task_ids]

    completions_by_date: Counter = Counter(c["occurrence_date"] for c in active_history)
    completions_30d_by_task: dict[int, int] = defaultdict(int)
    done_this_week = 0
    for c in active_history:
        if c["occurrence_date"] >= cutoff_30d:
            completions_30d_by_task[c["task_id"]] += 1
        if c["occurrence_date"] >= week_start:
            done_this_week += 1

    recurring_tasks = [t for t in all_tasks if t.get("recurrence_rule")]
    for t in recurring_tasks:
        c30 = completions_30d_by_task.get(t["id"], 0)
        exp = _expected_30d(t["recurrence_rule"])
        t["completions_30d"] = c30
        t["expected_30d"] = exp
        t["rate_30d"] = round(c30 / exp * 100) if exp > 0 else None

    recurring_tasks.sort(key=lambda t: (-(t.get("streak") or 0), t["title"]))
    best_streak = max((t.get("streak") or 0 for t in recurring_tasks), default=0)
    needs_attention = sum(1 for t in recurring_tasks if (t.get("missed_count") or 0) > 0)

    heatmap_weeks = _build_heatmap(completions_by_date, today)

    # ── LLM aggregations ─────────────────────────────────────────
    llm_by_model = dict(Counter(c["model"] for c in llm_calls).most_common())
    llm_by_feature = dict(Counter(c["feature"] for c in llm_calls).most_common(10))
    tokens_by_feature: dict[str, int] = defaultdict(int)
    for c in llm_calls:
        tokens_by_feature[c["feature"]] += (c.get("tokens_input") or 0) + (c.get("tokens_output") or 0)
    tokens_by_feature = dict(sorted(tokens_by_feature.items(), key=lambda kv: -kv[1])[:10])
    total_tokens_in = sum(c.get("tokens_input") or 0 for c in llm_calls)
    total_tokens_out = sum(c.get("tokens_output") or 0 for c in llm_calls)
    avg_latency = (
        sum(c.get("latency_ms") or 0 for c in llm_calls) / len(llm_calls)
        if llm_calls else 0
    )

    # ── Provider call aggregations ────────────────────────────────
    provider_by_name = dict(Counter(c["provider"] for c in provider_calls).most_common())
    provider_by_status = dict(Counter(c["status"] for c in provider_calls).most_common())

    # ── Command execution aggregations ────────────────────────────
    cmd_by_name = dict(Counter(c["command_name"] for c in cmd_executions).most_common(10))
    cmd_by_status = dict(Counter(c["status"] for c in cmd_executions).most_common())

    # ── Memory aggregations ───────────────────────────────────────
    memories_by_category = dict(Counter(m["category"] for m in memories_raw).most_common())

    # ── Paginate memories and working memory for display ─────────
    memories_page, memories_has_next, memories_has_prev = _pagination(memories_raw, 0)

    wm_show_expired = _parse_show_expired(request)
    wm_filtered, wm_expired_count = _filter_and_sort_working_memory(working_memories_raw, wm_show_expired)
    wm_page, wm_has_next, wm_has_prev = _pagination(wm_filtered, 0)
    wm_page = await _resolve_working_memory(wm_page)

    return templates.TemplateResponse(request, "insights.html", {
        # memories (paginated)
        "memories": memories_page,
        "memories_offset": 0,
        "memories_has_next": memories_has_next,
        "memories_has_prev": False,
        "memories_category": "",
        # working memory (paginated)
        "working_memories": wm_page,
        "wm_offset": 0,
        "wm_has_next": wm_has_next,
        "wm_has_prev": False,
        "wm_show_expired": wm_show_expired,
        "wm_expired_count": wm_expired_count,
        "now": today,
        # stats (computed from full fetch)
        "total_memories": len(memories_raw),
        "total_wm": len(wm_filtered),
        "memories_by_category": memories_by_category,
        # llm
        "llm_calls": llm_calls[:_LLM_CALLS_PREVIEW_SIZE],
        "provider_calls": provider_calls[:_PROVIDER_CALLS_PREVIEW_SIZE],
        "total_llm_calls": len(llm_calls),
        "total_tokens": total_tokens_in + total_tokens_out,
        "total_provider_calls": len(provider_calls),
        "avg_latency_ms": round(avg_latency),
        # task & habit
        "recurring_tasks": recurring_tasks,
        "heatmap_weeks": heatmap_weeks,
        "active_habits": len(recurring_tasks),
        "done_this_week": done_this_week,
        "best_streak": best_streak,
        "needs_attention": needs_attention,
        # chart data
        "llm_by_model": llm_by_model,
        "llm_by_feature": llm_by_feature,
        "tokens_by_feature": tokens_by_feature,
        "provider_by_name": provider_by_name,
        "provider_by_status": provider_by_status,
        "cmd_by_name": cmd_by_name,
        "cmd_by_status": cmd_by_status,
    })


async def _llm_call_filter_options() -> tuple[list[str], list[str]]:
    """Distinct models/features for the filter dropdowns, from a recent sample of calls."""
    try:
        raw = await api.get("/integration/llm-calls", params={"limit": _LLM_CALL_OPTIONS_LIMIT})
    except httpx.HTTPError:
        raw = []
    models = sorted({c["model"] for c in raw})
    features = sorted({c["feature"] for c in raw})
    return models, features


@router.get("/llm-calls", response_class=HTMLResponse)
async def llm_calls_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    model = request.query_params.get("model", "").strip()
    feature = request.query_params.get("feature", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if model:
        params["model"] = model
    if feature:
        params["feature"] = feature
    if q:
        params["q"] = q

    try:
        raw = await api.get("/integration/llm-calls", params=params)
    except httpx.HTTPError:
        raw = []

    calls, has_next, has_prev = _pagination(raw, offset)
    models, features = await _llm_call_filter_options()
    filter_qs = urlencode({k: v for k, v in {"model": model, "feature": feature, "q": q}.items() if v})

    return templates.TemplateResponse(request, "llm_calls.html", {
        "calls": calls,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "model": model,
        "feature": feature,
        "q": q,
        "models": models,
        "features": features,
        "filter_qs": filter_qs,
    })


async def _provider_call_filter_options() -> tuple[list[str], list[str], list[str], list[str]]:
    """Distinct providers/operations/entity types/statuses for the filter dropdowns, from a recent sample."""
    try:
        raw = await api.get("/integration/provider-calls", params={"limit": _PROVIDER_CALL_OPTIONS_LIMIT})
    except httpx.HTTPError:
        raw = []
    providers = sorted({c["provider"] for c in raw})
    operations = sorted({c["operation"] for c in raw})
    entity_types = sorted({c["entity_type"] for c in raw})
    statuses = sorted({c["status"] for c in raw})
    return providers, operations, entity_types, statuses


@router.get("/provider-calls", response_class=HTMLResponse)
async def provider_calls_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    provider = request.query_params.get("provider", "").strip()
    operation = request.query_params.get("operation", "").strip()
    entity_type = request.query_params.get("entity_type", "").strip()
    status = request.query_params.get("status", "").strip()
    q = request.query_params.get("q", "").strip()

    params: dict = {"limit": _PAGE_SIZE + 1, "skip": offset}
    if provider:
        params["provider"] = provider
    if operation:
        params["operation"] = operation
    if entity_type:
        params["entity_type"] = entity_type
    if status:
        params["status"] = status
    if q:
        params["q"] = q

    try:
        raw = await api.get("/integration/provider-calls", params=params)
    except httpx.HTTPError:
        raw = []

    calls, has_next, has_prev = _pagination(raw, offset)
    providers, operations, entity_types, statuses = await _provider_call_filter_options()
    filter_qs = urlencode({
        k: v for k, v in {
            "provider": provider, "operation": operation, "entity_type": entity_type, "status": status, "q": q,
        }.items() if v
    })

    return templates.TemplateResponse(request, "provider_calls.html", {
        "calls": calls,
        "offset": offset,
        "has_next": has_next,
        "has_prev": has_prev,
        "provider": provider,
        "operation": operation,
        "entity_type": entity_type,
        "status": status,
        "q": q,
        "providers": providers,
        "operations": operations,
        "entity_types": entity_types,
        "statuses": statuses,
        "filter_qs": filter_qs,
    })
