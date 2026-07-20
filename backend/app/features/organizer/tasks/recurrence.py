from datetime import date, timedelta

_BYDAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def parse_byday(rule: str) -> list[int] | None:
    for part in rule.split(";"):
        if part.startswith("BYDAY="):
            days = [d.strip().upper() for d in part[len("BYDAY="):].split(",")]
            result = [_BYDAY_MAP[d] for d in days if d in _BYDAY_MAP]
            return result if result else None
    return None


def is_due_today(rule: str, today: date) -> bool:
    if "FREQ=WEEKLY" in rule:
        byday = parse_byday(rule)
        if byday:
            return today.weekday() in byday
    return True


def is_done_in_cycle(rule: str, dates: list[date], today: date) -> bool:
    """Whether a completion covers the current occurrence, from its most recent due
    date (inclusive) through today — e.g. a Sunday-only habit stays "done" through the
    following Saturday once completed, not just on the day it was actually checked off."""
    if not dates:
        return False
    if "FREQ=WEEKLY" in rule:
        byday = parse_byday(rule)
        if byday:
            cycle_start = next(
                candidate
                for offset in range(7)
                if (candidate := today - timedelta(days=offset)).weekday() in byday
            )
            return any(cycle_start <= d <= today for d in dates)
        today_week = today.isocalendar()[:2]
        return any(d.isocalendar()[:2] == today_week for d in dates)
    if "FREQ=MONTHLY" in rule:
        return any((d.year, d.month) == (today.year, today.month) for d in dates)
    return today in dates


def compute_streak(dates: list[date], rule: str, today: date) -> int:
    if not dates:
        return 0
    sorted_dates = sorted(set(dates), reverse=True)

    if "FREQ=DAILY" in rule:
        if sorted_dates[0] < today - timedelta(days=1):
            return 0
        streak = 0
        expected = sorted_dates[0]
        for d in sorted_dates:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
        return streak

    elif "FREQ=WEEKLY" in rule:
        def _iso_week(d: date) -> tuple[int, int]:
            iso = d.isocalendar()
            return (iso[0], iso[1])

        weeks = sorted(set(_iso_week(d) for d in sorted_dates), reverse=True)
        if not weeks:
            return 0
        last_week = _iso_week(today - timedelta(weeks=1))
        if weeks[0] < last_week:
            return 0
        streak = 0
        yr, wk = weeks[0]
        for w_yr, w_wk in weeks:
            if (w_yr, w_wk) == (yr, wk):
                streak += 1
                prev = date.fromisocalendar(yr, wk, 1) - timedelta(weeks=1)
                yr, wk = _iso_week(prev)
            else:
                break
        return streak

    elif "FREQ=MONTHLY" in rule:
        def _month_key(d: date) -> tuple[int, int]:
            return (d.year, d.month)

        months = sorted(set(_month_key(d) for d in sorted_dates), reverse=True)
        if not months:
            return 0
        first_of_month = today.replace(day=1)
        last_month = _month_key(first_of_month - timedelta(days=1))
        if months[0] < last_month:
            return 0
        streak = 0
        yr, mo = months[0]
        for m_yr, m_mo in months:
            if (m_yr, m_mo) == (yr, mo):
                streak += 1
                prev = date(yr, mo, 1) - timedelta(days=1)
                yr, mo = prev.year, prev.month
            else:
                break
        return streak

    else:
        return len(sorted_dates)


def missed_count(rule: str, completions: list[date], today: date) -> int:
    completion_set = set(completions)

    if "FREQ=DAILY" in rule:
        return 0

    elif "FREQ=WEEKLY" in rule:
        week_start = today - timedelta(days=today.weekday())
        byday = parse_byday(rule)
        if byday:
            return sum(
                1
                for day_num in byday
                if (scheduled := week_start + timedelta(days=day_num)) < today
                and scheduled not in completion_set
            )
        else:
            if today.weekday() >= 4:
                return 0 if any(week_start <= d < today for d in completion_set) else 1
            return 0

    elif "FREQ=MONTHLY" in rule:
        if today.day >= 25:
            month_start = today.replace(day=1)
            return 0 if any(month_start <= d < today for d in completion_set) else 1
        return 0

    return 0
