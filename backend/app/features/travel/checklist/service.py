import logging
from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.tasks.schemas import TaskCreate, TaskFilters
from app.features.organizer.tasks.service import TaskService
from app.features.travel.checklist import template
from app.features.travel.checklist.schemas import ChecklistGenerated, ChecklistItemRead
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.trips.repository import TripRepository
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)

_DUE_TIME = time(23, 59)


def _read(item: template.ChecklistItem) -> ChecklistItemRead:
    return ChecklistItemRead(anchor=item.anchor, name=item.slug, title=item.title, offset_days=item.offset_days)


class ChecklistService:
    def __init__(self, session: AsyncSession, task_service: TaskService | None = None):
        self._settings = SettingService(session)
        self._trips = TripRepository(session)
        self._tasks = task_service

    async def _items(self) -> list[template.ChecklistItem]:
        """The template, writing the defaults the first time so that emptying the list later sticks."""
        if await self._settings.get_value(template.SEEDED_KEY) is None:
            for anchor, slug, offset in template.DEFAULT_ITEMS:
                await self._settings.set_value(template.make_key(anchor, slug), str(offset))
            await self._settings.set_value(template.SEEDED_KEY, "1")
            logger.info("Checklist template seeded: items=%d", len(template.DEFAULT_ITEMS))
        return template.parse_items(await self._settings.list_values(template.KEY_PREFIX))

    async def get_template(self) -> list[ChecklistItemRead]:
        return [_read(i) for i in await self._items()]

    async def put_item(self, anchor: str, name: str, offset_days: int) -> ChecklistItemRead:
        self._validate(anchor, name)
        existing = await self._items()
        if any(i.slug == name and i.anchor != anchor for i in existing):
            raise TravelConflictError(f"'{name}' already exists under the other anchor")
        await self._settings.set_value(template.make_key(anchor, name), str(offset_days))
        return _read(template.ChecklistItem(anchor, name, offset_days))  # type: ignore[arg-type]

    async def delete_item(self, anchor: str, name: str) -> bool:
        self._validate(anchor, name)
        return await self._settings.delete_value(template.make_key(anchor, name))

    @staticmethod
    def _validate(anchor: str, name: str) -> None:
        if anchor not in template.ANCHORS:
            raise ValueError(f"anchor must be one of {', '.join(template.ANCHORS)}")
        if not template.SLUG_PATTERN.match(name):
            raise ValueError("name may only contain lowercase letters, digits, '-' and '_'")

    async def generate(self, trip_id: int) -> ChecklistGenerated:
        """One task per template item, due at its offset from the trip; an item whose task already exists is skipped."""
        if self._tasks is None:
            raise RuntimeError("ChecklistService needs a TaskService to generate tasks")
        trip = await self._trips.get_trip(trip_id)
        if trip is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        today = local_today()
        created: list[str] = []
        skipped: list[str] = []
        for item in await self._items():
            title = f"{item.title} ({trip.name})"
            existing = await self._tasks.get_tasks(TaskFilters(
                limit=50, status="ALL", priority="ALL", urgency="ALL", tags=None, deadline_from=None, deadline_to=None,
                include_recurring=True, due_today=False, context=None, available=False, q=title,
            ))
            if any(t.title.lower() == title.lower() for t in existing):
                skipped.append(title)
                continue
            due = template.due_date(item, trip.start_date, trip.end_date, today)
            await self._tasks.create_task(TaskCreate(title=title, deadline=datetime.combine(due, _DUE_TIME)))
            created.append(title)
        logger.info("Checklist generated: trip_id=%d created=%d skipped=%d", trip_id, len(created), len(skipped))
        return ChecklistGenerated(created=created, skipped=skipped)
