import calendar
import hashlib
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.recurring_transactions.repository import RecurringTransactionRepository
from app.features.finance.recurring_transactions.schemas import (
    ProcessResult,
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import TransactionCreate

logger = logging.getLogger(__name__)


def _parse_rrule(rule: str) -> dict[str, str]:
    return {k: v for k, v in (p.split("=", 1) for p in rule.upper().split(";") if "=" in p)}


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _next_occurrence(rule: str, last: date) -> date | None:
    """Return the next occurrence after `last`, or None if the rule is exhausted."""
    parts = _parse_rrule(rule)
    freq = parts.get("FREQ", "")
    interval = int(parts.get("INTERVAL", "1"))

    if freq == "DAILY":
        next_date = last + timedelta(days=interval)
    elif freq == "WEEKLY":
        next_date = last + timedelta(weeks=interval)
    elif freq == "MONTHLY":
        next_date = _add_months(last, interval)
    elif freq == "YEARLY":
        next_date = _add_months(last, 12 * interval)
    else:
        return None

    until_str = parts.get("UNTIL")
    if until_str and len(until_str) >= 8:
        until = date(int(until_str[:4]), int(until_str[4:6]), int(until_str[6:8]))
        if next_date > until:
            return None

    count_str = parts.get("COUNT")
    if count_str:
        # COUNT is enforced by the caller tracking the number of occurrences created
        pass

    return next_date


class RecurringTransactionService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = RecurringTransactionRepository(session)
        self._session = session

    async def get(self, recurring_id: int) -> RecurringTransactionRead | None:
        rt = await self._repo.get(recurring_id)
        if rt is None:
            return None
        return RecurringTransactionRead.model_validate(rt)

    async def list(self, filters: RecurringTransactionFilters) -> list[RecurringTransactionRead]:
        rts = await self._repo.list(filters)
        return [RecurringTransactionRead.model_validate(r) for r in rts]

    async def create(self, data: RecurringTransactionCreate) -> RecurringTransactionRead:
        rt = await self._repo.create(data)
        logger.info("RecurringTransaction created: id=%d merchant=%r rule=%s", rt.id, data.merchant, data.recurrence_rule)
        return RecurringTransactionRead.model_validate(rt)

    async def update(
        self, recurring_id: int, data: RecurringTransactionUpdate
    ) -> RecurringTransactionRead | None:
        rt = await self._repo.update(recurring_id, data)
        if rt is None:
            logger.debug("RecurringTransaction update: id=%d not found", recurring_id)
            return None
        logger.info("RecurringTransaction updated: id=%d fields=%s", recurring_id, list(data.model_dump(exclude_unset=True).keys()))
        return RecurringTransactionRead.model_validate(rt)

    async def delete(self, recurring_id: int) -> bool:
        deleted = await self._repo.delete(recurring_id)
        if deleted:
            logger.info("RecurringTransaction deleted: id=%d", recurring_id)
        else:
            logger.debug("RecurringTransaction delete: id=%d not found", recurring_id)
        return deleted

    async def process(self) -> ProcessResult:
        """
        Materialize due transactions for all active recurring rules.
        Idempotent: uses deduplication hash to skip already-created occurrences.
        Deactivates rules whose RRULE is exhausted (UNTIL/COUNT reached).
        """
        today = date.today()
        active = await self._repo.list_active()
        txn_repo = TransactionRepository(self._session)
        created = 0
        deactivated = 0

        for rt in active:
            parts = _parse_rrule(rt.recurrence_rule)
            count_limit = int(parts["COUNT"]) if "COUNT" in parts else None
            occurrences_created = 0

            # First run: materialise today as the starting occurrence
            next_date: date | None = today if rt.last_occurrence_date is None else _next_occurrence(rt.recurrence_rule, rt.last_occurrence_date)

            while next_date is not None and next_date <= today:
                if count_limit is not None and occurrences_created >= count_limit:
                    next_date = None
                    break

                dedup_hash = hashlib.sha256(
                    f"recurring:{rt.id}:{next_date.isoformat()}".encode()
                ).hexdigest()

                if not await txn_repo.exists_by_dedup_hash(dedup_hash):
                    await txn_repo.add(TransactionCreate(
                        account_id=rt.account_id,
                        date=datetime.combine(next_date, datetime.min.time()),
                        amount=rt.amount,
                        currency=rt.currency,
                        type=rt.type,
                        category_id=rt.category_id,
                        merchant=rt.merchant,
                        source="recurring",
                        deduplication_hash=dedup_hash,
                    ))
                    created += 1
                    occurrences_created += 1
                    logger.info(
                        "Recurring transaction materialized: recurring_id=%d date=%s merchant=%r",
                        rt.id, next_date, rt.merchant,
                    )

                rt.last_occurrence_date = next_date
                next_date = _next_occurrence(rt.recurrence_rule, next_date)

            # Deactivate if the rule is now exhausted
            if next_date is None and rt.last_occurrence_date is not None:
                rt.active = False
                deactivated += 1
                logger.info(
                    "RecurringTransaction deactivated (exhausted): id=%d merchant=%r",
                    rt.id, rt.merchant,
                )

        await self._session.commit()
        logger.info("Recurring processing complete: created=%d deactivated=%d", created, deactivated)
        return ProcessResult(created=created, deactivated=deactivated)
