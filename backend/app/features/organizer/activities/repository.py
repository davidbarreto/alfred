from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.activities.schemas import ActivityCreate, ActivityFilters, ActivityLogCreate, ActivityUpdate
from app.features.organizer.activities.tables import Activity, ActivityLog
from app.features.organizer.tags.tables import Tag

# Activities are Alfred-only, so their tags live under one fixed provider id.
TAG_PROVIDER_ID = "alfred"
_ACTIVITY_EXCLUDE = {"tags"}


class ActivityRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_activity(self, activity_id: int) -> Activity | None:
        result = await self._session.execute(
            select(Activity)
            .options(selectinload(Activity.tags))
            .where(Activity.id == activity_id)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def get_activities(self, filters: ActivityFilters) -> list[Activity]:
        query = select(Activity).options(selectinload(Activity.tags))
        if not filters.include_archived:
            query = query.where(Activity.archived_at.is_(None))
        if filters.tag:
            query = query.where(Activity.tags.any(func.lower(Tag.name) == filters.tag.lower()))
        if filters.q:
            query = query.where(Activity.title.ilike(f"%{filters.q}%"))
        query = query.order_by(Activity.title, Activity.id).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, names: list[str]) -> list[Tag]:
        tags: list[Tag] = []
        unique = {}
        for name in (n.strip() for n in names):
            if name:
                unique.setdefault(name.lower(), name)  # first spelling wins
        for name in unique.values():
            result = await self._session.execute(
                select(Tag).where(Tag.provider_id == TAG_PROVIDER_ID, func.lower(Tag.name) == name.lower())
            )
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(provider_id=TAG_PROVIDER_ID, name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags

    async def create_activity(self, data: ActivityCreate) -> Activity:
        activity = Activity(**data.model_dump(exclude=_ACTIVITY_EXCLUDE))
        activity.tags = await self._resolve_tags(data.tags)
        self._session.add(activity)
        await self._session.commit()
        return await self._require(activity.id)

    async def update_activity(self, activity_id: int, data: ActivityUpdate) -> Activity | None:
        activity = await self.get_activity(activity_id)
        if activity is None:
            return None
        changes = data.model_dump(exclude_unset=True)
        if "tags" in changes:
            activity.tags = await self._resolve_tags(changes.pop("tags") or [])
        for field, value in changes.items():
            setattr(activity, field, value)
        await self._session.commit()
        return await self._require(activity_id)

    async def set_archived(self, activity_id: int, archived_at: datetime | None) -> Activity | None:
        activity = await self.get_activity(activity_id)
        if activity is None:
            return None
        activity.archived_at = archived_at
        await self._session.commit()
        return await self._require(activity_id)

    async def _require(self, activity_id: int) -> Activity:
        activity = await self.get_activity(activity_id)
        assert activity is not None
        return activity

    async def create_log(self, activity_id: int, data: ActivityLogCreate, done_at: datetime) -> ActivityLog:
        log = ActivityLog(activity_id=activity_id, done_at=done_at, minutes=data.minutes, note=data.note)
        self._session.add(log)
        await self._session.commit()
        return log

    async def get_logs(self, activity_id: int, limit: int, offset: int) -> list[ActivityLog]:
        result = await self._session.execute(
            select(ActivityLog)
            .where(ActivityLog.activity_id == activity_id)
            .order_by(ActivityLog.done_at.desc(), ActivityLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_last_done(self, activity_ids: list[int]) -> dict[int, datetime]:
        if not activity_ids:
            return {}
        result = await self._session.execute(
            select(ActivityLog.activity_id, func.max(ActivityLog.done_at))
            .where(ActivityLog.activity_id.in_(activity_ids))
            .group_by(ActivityLog.activity_id)
        )
        return {activity_id: done_at for activity_id, done_at in result.all()}

    async def count_logs_between(self, activity_ids: list[int], start: datetime, end: datetime) -> dict[int, int]:
        if not activity_ids:
            return {}
        result = await self._session.execute(
            select(ActivityLog.activity_id, func.count(ActivityLog.id))
            .where(ActivityLog.activity_id.in_(activity_ids), ActivityLog.done_at >= start, ActivityLog.done_at < end)
            .group_by(ActivityLog.activity_id)
        )
        return {activity_id: count for activity_id, count in result.all()}

    async def get_logs_since(self, since: datetime) -> list[tuple[ActivityLog, Activity]]:
        result = await self._session.execute(
            select(ActivityLog, Activity)
            .join(Activity, Activity.id == ActivityLog.activity_id)
            .options(selectinload(Activity.tags))
            .where(ActivityLog.done_at >= since)
            .order_by(ActivityLog.done_at)
        )
        return [(log, activity) for log, activity in result.all()]
