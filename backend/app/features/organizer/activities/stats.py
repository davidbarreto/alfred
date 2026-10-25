"""Pure aggregation of activity logs into weekly / per-activity / per-tag counts. No DB, no IO."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Sequence

from app.features.organizer.activities.schemas import ActivityStat, ActivityStats, TagStat, WeekStat


@dataclass(frozen=True)
class LogRow:
    activity_id: int
    title: str
    tags: tuple[str, ...]
    done_at: datetime  # naive local time, as LocalDateTime presents it
    minutes: int | None


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def week_starts(today: date, weeks: int) -> list[date]:
    """The last `weeks` Mondays up to and including the current week, oldest first."""
    current = monday_of(today)
    return [current - timedelta(weeks=offset) for offset in range(weeks - 1, -1, -1)]


def compute_stats(rows: Sequence[LogRow], starts: Sequence[date]) -> ActivityStats:
    window = set(starts)
    per_week = {start: [0, 0] for start in starts}
    per_activity: dict[int, list] = {}
    per_tag: dict[str, list[int]] = {}
    total_count = total_minutes = 0

    for row in rows:
        week = monday_of(row.done_at.date())
        if week not in window:
            continue
        minutes = row.minutes or 0
        per_week[week][0] += 1
        per_week[week][1] += minutes
        entry = per_activity.setdefault(row.activity_id, [row.title, 0, 0])
        entry[1] += 1
        entry[2] += minutes
        for tag in row.tags:
            tag_entry = per_tag.setdefault(tag, [0, 0])
            tag_entry[0] += 1
            tag_entry[1] += minutes
        total_count += 1
        total_minutes += minutes

    return ActivityStats(
        weeks=[WeekStat(week_start=s, count=per_week[s][0], minutes=per_week[s][1]) for s in starts],
        by_activity=[
            ActivityStat(activity_id=aid, title=title, count=count, minutes=minutes)
            for aid, (title, count, minutes) in sorted(per_activity.items(), key=lambda kv: (-kv[1][1], kv[1][0]))
        ],
        by_tag=[
            TagStat(tag=tag, count=count, minutes=minutes)
            for tag, (count, minutes) in sorted(per_tag.items(), key=lambda kv: (-kv[1][0], kv[0]))
        ],
        total_count=total_count,
        total_minutes=total_minutes,
    )
