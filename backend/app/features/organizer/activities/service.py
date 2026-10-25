import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.activities.repository import ActivityRepository
from app.features.organizer.activities.schemas import (
    ActivityCreate,
    ActivityFilters,
    ActivityLogCreate,
    ActivityLogRead,
    ActivityRead,
    ActivityStats,
    ActivitySuggestion,
    ActivityUpdate,
)
from app.features.organizer.activities.stats import LogRow, compute_stats, monday_of, week_starts
from app.features.organizer.activities.tables import Activity
from app.shared.timezone import local_naive_now, local_timezone, local_today

logger = logging.getLogger(__name__)

DEFAULT_STATS_WEEKS = 12
MAX_STATS_WEEKS = 104
_FUTURE_TOLERANCE = timedelta(minutes=5)


class ActivityValidationError(ValueError):
    """The request is well-formed but breaks a rule (maps to 422)."""


class ActivityStateError(ValueError):
    """The activity is in the wrong state for the request, e.g. logging an archived one (maps to 409)."""


def _current_week_window() -> tuple[datetime, datetime]:
    """Monday 00:00 to next Monday 00:00 in local time (naive, like LocalDateTime columns)."""
    start = datetime.combine(monday_of(local_today()), time.min)
    return start, start + timedelta(days=7)


def _naive_local(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(local_timezone()).replace(tzinfo=None)


class ActivityService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ActivityRepository(session)

    async def get_activities(self, filters: ActivityFilters) -> list[ActivityRead]:
        activities = await self._repo.get_activities(filters)
        return await self._with_progress(activities)

    async def get_activity(self, activity_id: int) -> ActivityRead | None:
        activity = await self._repo.get_activity(activity_id)
        if activity is None:
            return None
        return (await self._with_progress([activity]))[0]

    async def _with_progress(self, activities: list[Activity]) -> list[ActivityRead]:
        """Reads enriched with the last log time and, for activities with a weekly target, this week's count."""
        ids = [a.id for a in activities]
        last_done = await self._repo.get_last_done(ids)
        targeted = [a.id for a in activities if a.target_per_week]
        this_week = await self._repo.count_logs_between(targeted, *_current_week_window())
        return [
            self._read(a, last_done.get(a.id), this_week.get(a.id, 0) if a.target_per_week else None)
            for a in activities
        ]

    async def create_activity(self, data: ActivityCreate) -> ActivityRead:
        activity = await self._repo.create_activity(data)
        logger.info("Activity created: id=%d title=%r", activity.id, activity.title)
        return self._read(activity, None, 0 if activity.target_per_week else None)

    async def update_activity(self, activity_id: int, data: ActivityUpdate) -> ActivityRead | None:
        activity = await self._repo.get_activity(activity_id)
        if activity is None:
            logger.debug("Activity update: id=%d not found", activity_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        low = changes.get("min_minutes", activity.min_minutes)
        high = changes.get("max_minutes", activity.max_minutes)
        if low is not None and high is not None and high < low:
            raise ActivityValidationError("max_minutes must not be less than min_minutes")
        updated = await self._repo.update_activity(activity_id, data)
        logger.info("Activity updated: id=%d fields=%s", activity_id, list(changes.keys()))
        return (await self._with_progress([updated]))[0]

    async def archive(self, activity_id: int) -> ActivityRead | None:
        return await self._set_archived(activity_id, datetime.now(timezone.utc), "archived")

    async def unarchive(self, activity_id: int) -> ActivityRead | None:
        return await self._set_archived(activity_id, None, "unarchived")

    async def _set_archived(self, activity_id: int, archived_at: datetime | None, label: str) -> ActivityRead | None:
        activity = await self._repo.set_archived(activity_id, archived_at)
        if activity is None:
            logger.debug("Activity %s: id=%d not found", label, activity_id)
            return None
        logger.info("Activity %s: id=%d title=%r", label, activity_id, activity.title)
        return (await self._with_progress([activity]))[0]

    async def log(self, activity_id: int, data: ActivityLogCreate) -> ActivityLogRead | None:
        activity = await self._repo.get_activity(activity_id)
        if activity is None:
            logger.debug("Activity log: id=%d not found", activity_id)
            return None
        if activity.archived_at is not None:
            raise ActivityStateError(f"Activity {activity_id} is archived; unarchive it before logging")
        now = local_naive_now()
        done_at = _naive_local(data.done_at) if data.done_at is not None else now
        if done_at > now + _FUTURE_TOLERANCE:
            raise ActivityValidationError("done_at cannot be in the future")
        log = await self._repo.create_log(activity_id, data, done_at)
        logger.info("Activity logged: id=%d activity_id=%d has_minutes=%s", log.id, activity_id, data.minutes is not None)
        return ActivityLogRead.model_validate(log)

    async def get_history(self, activity_id: int, limit: int = 50, offset: int = 0) -> list[ActivityLogRead] | None:
        if await self._repo.get_activity(activity_id) is None:
            return None
        logs = await self._repo.get_logs(activity_id, limit, offset)
        return [ActivityLogRead.model_validate(log) for log in logs]

    async def get_stats(self, weeks: int = DEFAULT_STATS_WEEKS) -> ActivityStats:
        starts = week_starts(local_today(), weeks)
        rows = await self._repo.get_logs_since(datetime.combine(starts[0], time.min))
        log_rows = [
            LogRow(
                activity_id=activity.id,
                title=activity.title,
                tags=tuple(t.name for t in activity.tags),
                done_at=log.done_at,
                minutes=log.minutes,
            )
            for log, activity in rows
        ]
        return compute_stats(log_rows, starts)

    async def get_suggestions(self) -> list[ActivitySuggestion]:
        """Active activities, least recently done first (never done ones lead), with weekly progress."""
        activities = await self._repo.get_activities(ActivityFilters(limit=500))
        ids = [a.id for a in activities]
        last_done = await self._repo.get_last_done(ids)
        today = local_today()
        this_week = await self._repo.count_logs_between(ids, *_current_week_window())

        def sort_key(activity: Activity):
            done = last_done.get(activity.id)
            return (done is not None, done or datetime.min, activity.id)

        suggestions = []
        for activity in sorted(activities, key=sort_key):
            done = last_done.get(activity.id)
            suggestions.append(
                ActivitySuggestion(
                    id=activity.id,
                    title=activity.title,
                    min_minutes=activity.min_minutes,
                    max_minutes=activity.max_minutes,
                    context=activity.context,
                    tags=[t.name for t in activity.tags] or None,
                    days_since_last_done=(today - done.date()).days if done is not None else None,
                    target_per_week=activity.target_per_week,
                    done_this_week=this_week.get(activity.id, 0) if activity.target_per_week else None,
                )
            )
        return suggestions

    @staticmethod
    def _read(activity: Activity, last_done: datetime | None, done_this_week: int | None = None) -> ActivityRead:
        return ActivityRead.model_validate(activity).model_copy(
            update={"last_done_at": last_done, "done_this_week": done_this_week}
        )
