from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/tasks/insights")

_WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_TIME_TO_COMPLETE_BUCKETS = [
    ("<1h", timedelta(hours=1)),
    ("<1d", timedelta(days=1)),
    ("<3d", timedelta(days=3)),
    ("<1wk", timedelta(weeks=1)),
]
_TIME_TO_COMPLETE_OVERFLOW = ">1wk"


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


def _time_to_complete_bucket(delta: timedelta) -> str:
    for label, threshold in _TIME_TO_COMPLETE_BUCKETS:
        if delta < threshold:
            return label
    return _TIME_TO_COMPLETE_OVERFLOW


@router.get("", response_class=HTMLResponse)
async def tasks_insights_page(request: Request):
    all_tasks, task_history = [], []

    for path, params, target in [
        ("/organizer/tasks", {"status": "ALL", "limit": 200}, "tasks"),
        ("/organizer/tasks/history", {"days": 90}, "task_history"),
    ]:
        try:
            result = await api.get(path, params=params)
            if target == "tasks":
                all_tasks = result
            elif target == "task_history":
                task_history = result
        except httpx.HTTPError:
            pass

    today = date.today()
    today_str = today.isoformat()
    week_start = (today - timedelta(days=today.weekday())).isoformat()
    cutoff_30d = (today - timedelta(days=30)).isoformat()

    active_task_ids = {t["id"] for t in all_tasks}
    active_history = [c for c in task_history if c["task_id"] in active_task_ids]

    # ── Habit stats ─────────────────────────────────────────────
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
    missed_habits = [t for t in recurring_tasks if (t.get("missed_count") or 0) > 0]
    needs_attention = len(missed_habits)

    heatmap_weeks = _build_heatmap(completions_by_date, today)

    # ── Missed one-off tasks ──────────────────────────────────────
    missed_one_off = [
        t for t in all_tasks
        if not t.get("recurrence_rule")
        and t.get("deadline")
        and t["deadline"][:10] < today_str
        and t["status"] not in ("DONE", "CANCELLED")
    ]
    missed_one_off.sort(key=lambda t: t["deadline"])

    # ── Productivity by day of week ────────────────────────────────
    weekday_counts: Counter = Counter()
    for t in all_tasks:
        if t.get("completed_at"):
            weekday_counts[date.fromisoformat(t["completed_at"][:10]).strftime("%a")] += 1
    for c in active_history:
        weekday_counts[date.fromisoformat(c["occurrence_date"]).strftime("%a")] += 1
    by_weekday = {day: weekday_counts[day] for day in _WEEKDAY_ORDER if weekday_counts[day]}

    # ── Completion rate by priority (one-off tasks only) ───────────
    priority_totals: Counter = Counter()
    priority_done: Counter = Counter()
    for t in all_tasks:
        if t.get("recurrence_rule") or t["status"] == "CANCELLED":
            continue
        priority_totals[t["priority"]] += 1
        if t["status"] == "DONE":
            priority_done[t["priority"]] += 1
    completion_rate_by_priority = {
        p: round(priority_done[p] / priority_totals[p] * 100)
        for p in ("HIGH", "MEDIUM", "LOW") if priority_totals[p]
    }

    # ── Time to complete (one-off tasks only) ───────────────────────
    time_to_complete: Counter = Counter()
    for t in all_tasks:
        if t.get("recurrence_rule") or not t.get("completed_at") or not t.get("created_at"):
            continue
        completed = datetime.fromisoformat(t["completed_at"].replace("Z", "+00:00"))
        created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
        time_to_complete[_time_to_complete_bucket(completed - created)] += 1
    time_to_complete_chart = {
        label: time_to_complete[label]
        for label, _ in _TIME_TO_COMPLETE_BUCKETS + [(_TIME_TO_COMPLETE_OVERFLOW, None)]
        if time_to_complete[label]
    }

    return templates.TemplateResponse(request, "tasks_insights.html", {
        # habits
        "recurring_tasks": recurring_tasks,
        "heatmap_weeks": heatmap_weeks,
        "active_habits": len(recurring_tasks),
        "done_this_week": done_this_week,
        "best_streak": best_streak,
        "needs_attention": needs_attention,
        # missed
        "missed_one_off": missed_one_off,
        "missed_habits": missed_habits,
        # charts
        "by_weekday": by_weekday,
        "completion_rate_by_priority": completion_rate_by_priority,
        "time_to_complete": time_to_complete_chart,
    })
