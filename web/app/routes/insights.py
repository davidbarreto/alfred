from collections import Counter, defaultdict
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/insights")

_PAGE_SIZE = 20


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    """Return (page_slice, has_next, has_prev) using the limit+1 trick."""
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


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


@router.get("/working-memory-section", response_class=HTMLResponse)
async def working_memory_section(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    try:
        raw = await api.get("/core/working-memory", params={"active_only": "false", "limit": _PAGE_SIZE + 1, "offset": offset})
    except httpx.HTTPError:
        raw = []
    wm_sorted = sorted(raw, key=lambda w: (w.get("expires_at") or ""))
    working_memories, wm_has_next, wm_has_prev = _pagination(wm_sorted, offset)
    return templates.TemplateResponse(request, "_working_memory_list.html", {
        "working_memories": working_memories,
        "wm_offset": offset,
        "wm_has_next": wm_has_next,
        "wm_has_prev": wm_has_prev,
        "now": date.today(),
    })


@router.delete("/working-memory/{item_id}", response_class=HTMLResponse)
async def delete_working_memory(item_id: int, request: Request):
    try:
        await api.delete(f"/core/working-memory/{item_id}")
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to delete entry.</p>', status_code=422)

    try:
        raw = await api.get("/core/working-memory", params={"active_only": "false", "limit": _PAGE_SIZE + 1, "offset": 0})
    except httpx.HTTPError:
        raw = []

    wm_sorted = sorted(raw, key=lambda w: (w.get("expires_at") or ""))
    working_memories, wm_has_next, wm_has_prev = _pagination(wm_sorted, 0)
    return templates.TemplateResponse(request, "_working_memory_list.html", {
        "working_memories": working_memories,
        "wm_offset": 0,
        "wm_has_next": wm_has_next,
        "wm_has_prev": False,
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

    wm_sorted = sorted(working_memories_raw, key=lambda w: (w.get("expires_at") or ""))
    wm_page, wm_has_next, wm_has_prev = _pagination(wm_sorted, 0)

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
        "now": today,
        # stats (computed from full fetch)
        "total_memories": len(memories_raw),
        "total_wm": len(wm_sorted),
        "memories_by_category": memories_by_category,
        # llm
        "llm_calls": llm_calls[:20],
        "provider_calls": provider_calls[:20],
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
        "provider_by_name": provider_by_name,
        "provider_by_status": provider_by_status,
        "cmd_by_name": cmd_by_name,
        "cmd_by_status": cmd_by_status,
    })
