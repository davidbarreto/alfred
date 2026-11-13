"""Pure builders for the dashboard cards: backend payloads in, template-ready context out."""
from datetime import date, datetime, time, timedelta

CARD_CAP = 5
SPARK_DAYS = 14
SPARK_WIDTH = 100
SPARK_HEIGHT = 24
BIRTHDAY_WINDOW_DAYS = 30
BUDGET_ROWS = 3
METRIC_CARDS = 4
EVENING_FROM = time(21, 30)  # when the evening digest cron runs


def _aware(value: str, now: datetime) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=now.tzinfo)


def task_alerts(tasks: list[dict], now: datetime) -> dict:
    """Counts of overdue and URGENT tasks among the open ones."""
    overdue = 0
    for task in tasks:
        if task.get("deadline") and _aware(task["deadline"], now) < now and not task.get("is_done_in_cycle"):
            overdue += 1
    return {"overdue": overdue, "urgent": sum(1 for t in tasks if t.get("urgency") == "URGENT")}


def plan_card(plans: list[dict] | None, today: date, now_clock: str) -> dict | None:
    """Today's active plan: progress plus the blocks from the one in progress onward (capped)."""
    plan = next((p for p in plans or [] if p["plan_date"] == today.isoformat() and not p.get("archived_at")), None)
    if plan is None:
        return None
    blocks = [
        {**item, "start_clock": item["start"][11:16], "end_clock": item["end"][11:16]}
        for item in plan["items"]
    ]
    for block in blocks:
        block["current"] = block["start_clock"] <= now_clock < block["end_clock"]
    upcoming = [b for b in blocks if b["end_clock"] > now_clock]
    return {
        "total": len(blocks),
        "done": sum(1 for b in blocks if b.get("done")),
        "missed": sum(1 for b in blocks if b.get("missed")),
        "blocks": upcoming[:CARD_CAP],
        "more": max(len(upcoming) - CARD_CAP, 0),
        "finished": bool(blocks) and not upcoming,
    }


def trip_card(trips: list[dict] | None, detail: dict | None, today: date, other_events: list[dict] | None = None) -> dict | None:
    """The ongoing trip, else the nearest upcoming one, with the count of everything its warnings page lists."""
    if not trips:
        return None
    trip = min(trips, key=lambda t: t["start_date"])
    start, end = date.fromisoformat(trip["start_date"]), date.fromisoformat(trip["end_date"])
    ongoing = start <= today
    return {
        "id": trip["id"],
        "name": trip["name"],
        "start": start,
        "end": end,
        "ongoing": ongoing,
        "days_until": (start - today).days,
        "day": (today - start).days + 1,
        "days": (end - start).days + 1,
        "warnings": len((detail or {}).get("warnings") or []) + len(other_events or []),
    }


def sparkline(values: list[float]) -> str:
    """SVG polyline points scaled into the sparkline box (a flat series sits mid-height)."""
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = high - low
    step = SPARK_WIDTH / (len(values) - 1)
    pad = 2
    points = []
    for index, value in enumerate(values):
        ratio = 0.5 if span == 0 else (value - low) / span
        points.append(f"{index * step:.1f},{SPARK_HEIGHT - pad - ratio * (SPARK_HEIGHT - 2 * pad):.1f}")
    return " ".join(points)


def metric_card(series: dict, daily: dict | None, today: date) -> dict:
    """One series as a 14-day sparkline: counts use entries per day, other kinds the daily total."""
    by_day = {p["date"]: p for p in (daily or {}).get("points", [])}
    use_count = series["kind"] == "count"
    values = []
    for offset in range(SPARK_DAYS - 1, -1, -1):
        point = by_day.get((today - timedelta(days=offset)).isoformat())
        values.append(float((point["n"] if use_count else point["total"]) or 0) if point else 0.0)
    return {
        "name": series["name"],
        "unit": series.get("unit"),
        "kind": series["kind"],
        "today": values[-1],
        "week": sum(values[-7:]),
        "points": sparkline(values),
    }


def pick_series(series: list[dict] | None) -> list[dict]:
    """The most-used active series, one dashboard card each."""
    active = [s for s in series or [] if not s["is_archived"] and s["entry_count"]]
    return sorted(active, key=lambda s: -s["entry_count"])[:METRIC_CARDS]


def budget_rows(statuses: list[dict] | None) -> list[dict]:
    """The categories closest to (or over) their monthly limit."""
    rows = []
    for status in statuses or []:
        limit = float(status["limit_amount"] or 0)
        if limit <= 0:
            continue
        spent = float(status["spent"])
        rows.append({"name": status["category_name"], "spent": spent, "limit": limit, "ratio": spent / limit})
    rows.sort(key=lambda r: -r["ratio"])
    return rows[:BUDGET_ROWS]


def _next_birthday(born: date, today: date) -> date:
    def on_year(year: int) -> date:
        try:
            return born.replace(year=year)
        except ValueError:  # 29 Feb in a non-leap year
            return date(year, 3, 1)

    upcoming = on_year(today.year)
    return upcoming if upcoming >= today else on_year(today.year + 1)


def upcoming_birthdays(contacts: list[dict] | None, today: date) -> list[dict]:
    """Contacts with a birthday in the next 30 days, soonest first (capped)."""
    found = []
    for contact in contacts or []:
        if not contact.get("birthday") or contact.get("is_self"):
            continue
        when = _next_birthday(date.fromisoformat(contact["birthday"]), today)
        days = (when - today).days
        if days <= BIRTHDAY_WINDOW_DAYS:
            found.append({"name": contact["name"], "date": when, "days_until": days})
    found.sort(key=lambda b: (b["days_until"], b["name"]))
    return found[:CARD_CAP]


def todays_events(events: list[dict] | None, today: date) -> list[dict]:
    """Events happening today: those starting today plus multi-day ones that started earlier and still run.

    The API returns naive local ISO datetimes. Running events get `ends_on` so the card can say "until ..."
    instead of a clock range that belongs to another day.
    """
    iso = today.isoformat()
    found = []
    for event in events or []:
        starts, ends = event["start_datetime"][:10], event["end_datetime"][:10]
        if starts <= iso <= ends:
            found.append({**event, "ends_on": date.fromisoformat(ends) if starts < iso else None})
    return found


def upcoming_events(events: list[dict] | None) -> dict:
    """Events after today from the morning briefing's look-ahead (today's have their own strip), capped."""
    later = [e for e in events or [] if not e.get("is_today")]
    return {"items": later[:CARD_CAP], "more": max(len(later) - CARD_CAP, 0)}


def study_card(overview: dict | None) -> list[dict]:
    """Active study plans with progress and the next open item."""
    cards = []
    for plan in (overview or {}).get("active", []):
        items = plan["items"]
        pending = [i for i in items if not i["is_done"]]
        cards.append({
            "title": plan["title"],
            "done": len(items) - len(pending),
            "total": len(items),
            "next": pending[0]["description"] if pending else None,
        })
    return cards[:CARD_CAP]


def language_card(tracks: list[dict] | None, progress: list[dict] | None) -> list[dict]:
    """Each active track with today's reviews against its daily quota."""
    by_track = {p["track_id"]: p for p in progress or []}
    rows = []
    for track in tracks or []:
        done = by_track.get(track["id"])
        if done is None:
            continue
        rows.append({
            "name": track["name"],
            "completed_today": done["completed_today"],
            "daily_quota": done["daily_quota"],
            "quota_met": done["quota_met"],
        })
    return rows[:CARD_CAP]


def briefing_type(now: datetime) -> str:
    """Which saved briefing the dashboard shows: the evening digest at night, the morning briefing otherwise."""
    return "evening" if now.time() >= EVENING_FROM else "morning"
