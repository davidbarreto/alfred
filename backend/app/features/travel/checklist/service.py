import logging
from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.tasks.schemas import TaskCreate, TaskFilters
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.service import TaskService
from app.features.travel.checklist import template
from app.features.travel.checklist.schemas import (
    ChecklistGenerated,
    ChecklistItemRead,
    ChecklistItemWrite,
    ChecklistTemplateRead,
)
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.trips.repository import TripRepository
from app.shared.utils.timezone import local_today

logger = logging.getLogger(__name__)

_DUE_TIME = time(23, 59)


def _read(item: template.ChecklistItem) -> ChecklistItemRead:
    return ChecklistItemRead(anchor=item.anchor, name=item.slug, title=item.title, offset_days=item.offset_days)


class ChecklistService:
    def __init__(self, session: AsyncSession, task_service: TaskService | None = None):
        self._settings = SettingService(session)
        self._trips = TripRepository(session)
        self._tasks = task_service
        self._task_repo = TaskRepository(session)

    async def _items(self) -> list[template.ChecklistItem]:
        """The template, writing the defaults the first time so that emptying the list later sticks."""
        if await self._settings.get_value(template.SEEDED_KEY) is None:
            for anchor, slug, offset in template.DEFAULT_ITEMS:
                await self._settings.set_value(template.make_key(anchor, slug), str(offset))
            await self._settings.set_value(template.SEEDED_KEY, "1")
            logger.info("Checklist template seeded: items=%d", len(template.DEFAULT_ITEMS))
        return template.parse_items(await self._settings.list_values(template.KEY_PREFIX))

    async def is_pending(self, trip_name: str) -> bool:
        """The template has items but none of its tasks exists for this trip yet."""
        if not await self._items():
            return False
        suffix = f"({trip_name})".lower()
        found = await self._task_repo.get_tasks(TaskFilters(
            limit=50, status="ALL", priority="ALL", urgency="ALL", tags=None, deadline_from=None, deadline_to=None,
            include_recurring=True, due_today=False, context=None, available=False, q=suffix,
        ))
        return not any(t.title.lower().endswith(suffix) for t in found)

    async def get_template(self) -> ChecklistTemplateRead:
        return ChecklistTemplateRead(items=[_read(i) for i in await self._items()])

    async def replace_template(self, items: list[ChecklistItemWrite]) -> ChecklistTemplateRead:
        """Store exactly `items` (validated by the schema): new and changed ones are written, missing ones deleted."""
        current = {i.key: str(i.offset_days) for i in await self._items()}
        wanted = {template.make_key(i.anchor, i.name): str(i.offset_days) for i in items}
        for key in current.keys() - wanted.keys():
            await self._settings.delete_value(key)
        changed = [key for key, value in wanted.items() if current.get(key) != value]
        for key in changed:
            await self._settings.set_value(key, wanted[key])
        logger.info(
            "Checklist template replaced: items=%d written=%d deleted=%d",
            len(wanted), len(changed), len(current.keys() - wanted.keys()),
        )
        return await self.get_template()

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
            title = f"{item.title[:1].upper()}{item.title[1:]} ({trip.name})"
            existing = await self._tasks.get_tasks(TaskFilters(
                limit=50, status="ALL", priority="ALL", urgency="ALL", tags=None, deadline_from=None, deadline_to=None,
                include_recurring=True, due_today=False, context=None, available=False, q=title,
            ))
            if any(t.title.lower() == title.lower() for t in existing):
                skipped.append(title)
                continue
            due = template.due_date(item, trip.start_date, trip.end_date, today)
            await self._tasks.create_task(TaskCreate(title=title, priority="MEDIUM", deadline=datetime.combine(due, _DUE_TIME)))
            created.append(title)
        logger.info("Checklist generated: trip_id=%d created=%d skipped=%d", trip_id, len(created), len(skipped))
        return ChecklistGenerated(created=created, skipped=skipped)
