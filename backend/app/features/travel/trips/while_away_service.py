import logging
from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.recurring_transactions.repository import RecurringTransactionRepository
from app.features.finance.recurring_transactions.service import next_occurrence
from app.features.organizer.contacts.repository import ContactRepository
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters
from app.shared.timezone import local_today
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.while_away import (
    AwayBirthday, AwayCharge, AwayTask, WhileAway, birthdays_between, occurrences_between,
)

logger = logging.getLogger(__name__)


class WhileAwayService:
    def __init__(self, session: AsyncSession):
        self._trips = TripRepository(session)
        self._contacts = ContactRepository(session)
        self._tasks = TaskRepository(session)
        self._recurring = RecurringTransactionRepository(session)

    async def get_while_away(self, trip_id: int) -> WhileAway | None:
        trip = await self._trips.get_trip(trip_id)
        if trip is None:
            return None
        start, end = trip.start_date, trip.end_date
        today = local_today()

        birthdays = [
            AwayBirthday(contact_id=c.id, name=c.name, date=day)
            for c in await self._contacts.get_all_with_birthday()
            for day in birthdays_between(c.birthday, start, end)
        ]
        tasks = await self._tasks.get_tasks(TaskFilters(
            limit=200, status="ACTIVE", priority="ALL", urgency="ALL", tags=None,
            deadline_from=datetime.combine(start, time.min), deadline_to=datetime.combine(end, time.max),
            include_recurring=False, due_today=False, context=None, available=False, q=None,
        ))
        charges = [
            AwayCharge(
                recurring_id=r.id, merchant=r.merchant, amount=r.amount, currency=r.currency, date=day,
            )
            for r in await self._recurring.list_active() if r.type == "expense"
            for day in occurrences_between(r.recurrence_rule, r.last_occurrence_date, start, end, next_occurrence, today)
        ]
        result = WhileAway(
            trip_id=trip_id,
            birthdays=sorted(birthdays, key=lambda b: (b.date, b.name)),
            tasks=sorted((AwayTask(task_id=t.id, title=t.title, due=t.deadline.date()) for t in tasks if t.deadline),
                         key=lambda t: (t.due, t.title)),
            charges=sorted(charges, key=lambda c: (c.date, c.merchant or "")),
        )
        logger.debug("While away: trip_id=%d birthdays=%d tasks=%d charges=%d", trip_id,
                     len(result.birthdays), len(result.tasks), len(result.charges))
        return result
