from collections import Counter, defaultdict
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/insights")


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
    memories, llm_calls, provider_calls, cmd_executions = [], [], [], []
    all_tasks, task_history = [], []

    for path, params, target in [
        ("/core/memories/", {"limit": 200}, "memories"),
        ("/integration/llm-calls/", {"limit": 200}, "llm_calls"),
        ("/integration/provider-calls/", {"limit": 200}, "provider_calls"),
        ("/core/command-executions/", {"limit": 200}, "cmd_executions"),
        ("/organizer/tasks/", {"status": "ALL", "limit": 200}, "tasks"),
        ("/organizer/tasks/history", {"days": 90}, "task_history"),
    ]:
        try:
            result = await api.get(path, params=params)
            if target == "memories":         memories = result
            elif target == "llm_calls":      llm_calls = result
            elif target == "provider_calls": provider_calls = result
            elif target == "cmd_executions": cmd_executions = result
            elif target == "tasks":          all_tasks = result
            elif target == "task_history":   task_history = result
        except httpx.HTTPError:
            pass

    # ── Task & habit metrics ──────────────────────────────────────
    today = date.today()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    cutoff_30d = (today - timedelta(days=30)).isoformat()

    completions_by_date: Counter = Counter(c["occurrence_date"] for c in task_history)
    completions_30d_by_task: dict[int, int] = defaultdict(int)
    done_this_week = 0
    for c in task_history:
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
    memories_by_category = dict(Counter(m["category"] for m in memories).most_common())

    return templates.TemplateResponse(request, "insights.html", {
        "memories": memories,
        "llm_calls": llm_calls[:20],
        "provider_calls": provider_calls[:20],
        # task & habit
        "recurring_tasks": recurring_tasks,
        "heatmap_weeks": heatmap_weeks,
        "active_habits": len(recurring_tasks),
        "done_this_week": done_this_week,
        "best_streak": best_streak,
        "needs_attention": needs_attention,
        # stat cards
        "total_memories": len(memories),
        "total_llm_calls": len(llm_calls),
        "total_tokens": total_tokens_in + total_tokens_out,
        "total_provider_calls": len(provider_calls),
        # chart data
        "llm_by_model": llm_by_model,
        "llm_by_feature": llm_by_feature,
        "provider_by_name": provider_by_name,
        "provider_by_status": provider_by_status,
        "cmd_by_name": cmd_by_name,
        "cmd_by_status": cmd_by_status,
        "memories_by_category": memories_by_category,
        # derived
        "avg_latency_ms": round(avg_latency),
    })
