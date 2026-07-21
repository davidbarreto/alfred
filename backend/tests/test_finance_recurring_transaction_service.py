import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.recurring_transactions.service import (
    RecurringTransactionService,
    _add_months,
    _next_occurrence,
)
from app.features.finance.recurring_transactions.schemas import (
    ProcessResult,
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)


def _make_rt_orm(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.account_id = kwargs.get("account_id", 1)
    r.category_id = kwargs.get("category_id", None)
    r.type = kwargs.get("type", "expense")
    r.amount = kwargs.get("amount", Decimal("9.99"))
    r.currency = kwargs.get("currency", "EUR")
    r.merchant = kwargs.get("merchant", "Streaming")
    r.recurrence_rule = kwargs.get("recurrence_rule", "FREQ=MONTHLY")
    r.active = kwargs.get("active", True)
    r.last_occurrence_date = kwargs.get("last_occurrence_date", None)
    return r


@pytest.fixture
def service():
    svc = RecurringTransactionService.__new__(RecurringTransactionService)
    svc._repo = AsyncMock()
    svc._session = AsyncMock()
    svc._fx = AsyncMock()
    svc._fx.convert_to_eur.return_value = None
    return svc


class TestGet:
    async def test_returns_read_when_found(self, service):
        service._repo.get.return_value = _make_rt_orm()
        result = await service.get(1)
        assert isinstance(result, RecurringTransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_reads(self, service):
        service._repo.list.return_value = [_make_rt_orm(id=i) for i in range(3)]
        result = await service.list(RecurringTransactionFilters())
        assert len(result) == 3
        assert all(isinstance(r, RecurringTransactionRead) for r in result)

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = RecurringTransactionFilters(active=True, type="expense")
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list(RecurringTransactionFilters()) == []


class TestCreate:
    async def test_returns_recurring_transaction_read(self, service):
        service._repo.create.return_value = _make_rt_orm()
        result = await service.create(RecurringTransactionCreate(
            account_id=1, type="expense", amount=Decimal("9.99"),
            recurrence_rule="FREQ=MONTHLY",
        ))
        assert isinstance(result, RecurringTransactionRead)


class TestUpdate:
    async def test_returns_read_when_found(self, service):
        service._repo.update.return_value = _make_rt_orm(amount=Decimal("12.99"))
        result = await service.update(1, RecurringTransactionUpdate(amount=Decimal("12.99")))
        assert isinstance(result, RecurringTransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, RecurringTransactionUpdate(active=False)) is None


class TestDelete:
    async def test_passes_through_true(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_passes_through_false(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False


class TestNextOccurrence:
    def test_monthly_advances_one_month(self):
        result = _next_occurrence("FREQ=MONTHLY", date(2026, 1, 15))
        assert result == date(2026, 2, 15)

    def test_monthly_clamps_end_of_month(self):
        result = _next_occurrence("FREQ=MONTHLY", date(2026, 1, 31))
        assert result == date(2026, 2, 28)

    def test_weekly_advances_seven_days(self):
        result = _next_occurrence("FREQ=WEEKLY", date(2026, 1, 1))
        assert result == date(2026, 1, 8)

    def test_biweekly_via_interval(self):
        result = _next_occurrence("FREQ=WEEKLY;INTERVAL=2", date(2026, 1, 1))
        assert result == date(2026, 1, 15)

    def test_daily_advances_one_day(self):
        result = _next_occurrence("FREQ=DAILY", date(2026, 1, 1))
        assert result == date(2026, 1, 2)

    def test_yearly_advances_one_year(self):
        result = _next_occurrence("FREQ=YEARLY", date(2026, 3, 1))
        assert result == date(2027, 3, 1)

    def test_until_on_boundary_is_included(self):
        # Occurrence landing on the UNTIL date is still valid
        result = _next_occurrence("FREQ=MONTHLY;UNTIL=20260101", date(2025, 12, 1))
        assert result == date(2026, 1, 1)

    def test_until_exhausted_returns_none(self):
        # Occurrence after UNTIL → exhausted
        result = _next_occurrence("FREQ=MONTHLY;UNTIL=20260101", date(2026, 1, 1))
        assert result is None

    def test_until_not_yet_reached(self):
        result = _next_occurrence("FREQ=MONTHLY;UNTIL=20261201", date(2026, 10, 1))
        assert result == date(2026, 11, 1)


class TestAddMonths:
    def test_basic(self):
        assert _add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_year_rollover(self):
        assert _add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)

    def test_clamps_short_month(self):
        assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


class TestProcess:
    async def test_creates_transaction_on_first_run(self, service):
        rt = _make_rt_orm(last_occurrence_date=None, recurrence_rule="FREQ=MONTHLY")
        service._repo.list_active.return_value = [rt]

        with patch(
            "app.features.finance.recurring_transactions.service.TransactionRepository"
        ) as MockTxnRepo:
            mock_txn_repo = AsyncMock()
            mock_txn_repo.exists_by_dedup_hash.return_value = False
            MockTxnRepo.return_value = mock_txn_repo

            with patch("app.features.finance.recurring_transactions.service.date") as mock_date:
                mock_date.today.return_value = date(2026, 7, 1)
                mock_date.side_effect = lambda *a, **k: date(*a, **k)
                result = await service.process()

        assert result.created == 1
        assert result.deactivated == 0
        mock_txn_repo.add.assert_called_once()

    async def test_materialized_transaction_carries_amount_eur(self, service):
        rt = _make_rt_orm(
            last_occurrence_date=None, recurrence_rule="FREQ=MONTHLY", currency="USD"
        )
        service._repo.list_active.return_value = [rt]
        service._fx.convert_to_eur.return_value = Decimal("8.50")

        with patch(
            "app.features.finance.recurring_transactions.service.TransactionRepository"
        ) as MockTxnRepo:
            mock_txn_repo = AsyncMock()
            mock_txn_repo.exists_by_dedup_hash.return_value = False
            MockTxnRepo.return_value = mock_txn_repo

            with patch("app.features.finance.recurring_transactions.service.date") as mock_date:
                mock_date.today.return_value = date(2026, 7, 1)
                mock_date.side_effect = lambda *a, **k: date(*a, **k)
                await service.process()

        service._fx.convert_to_eur.assert_awaited_once_with(rt.amount, "USD", date(2026, 7, 1))
        assert mock_txn_repo.add.call_args.kwargs["amount_eur"] == Decimal("8.50")

    async def test_idempotent_when_already_created(self, service):
        rt = _make_rt_orm(last_occurrence_date=date(2026, 6, 1), recurrence_rule="FREQ=MONTHLY")
        service._repo.list_active.return_value = [rt]

        with patch(
            "app.features.finance.recurring_transactions.service.TransactionRepository"
        ) as MockTxnRepo:
            mock_txn_repo = AsyncMock()
            mock_txn_repo.exists_by_dedup_hash.return_value = True
            MockTxnRepo.return_value = mock_txn_repo

            with patch("app.features.finance.recurring_transactions.service.date") as mock_date:
                mock_date.today.return_value = date(2026, 7, 1)
                mock_date.side_effect = lambda *a, **k: date(*a, **k)
                result = await service.process()

        assert result.created == 0
        mock_txn_repo.add.assert_not_called()

    async def test_deactivates_when_until_exhausted(self, service):
        rt = _make_rt_orm(
            last_occurrence_date=date(2026, 6, 1),
            recurrence_rule="FREQ=MONTHLY;UNTIL=20260601",
        )
        service._repo.list_active.return_value = [rt]

        with patch(
            "app.features.finance.recurring_transactions.service.TransactionRepository"
        ) as MockTxnRepo:
            mock_txn_repo = AsyncMock()
            mock_txn_repo.exists_by_dedup_hash.return_value = True
            MockTxnRepo.return_value = mock_txn_repo

            with patch("app.features.finance.recurring_transactions.service.date") as mock_date:
                mock_date.today.return_value = date(2026, 7, 1)
                mock_date.side_effect = lambda *a, **k: date(*a, **k)
                result = await service.process()

        assert result.deactivated == 1
        assert rt.active is False

    async def test_no_active_rules_returns_zeros(self, service):
        service._repo.list_active.return_value = []
        result = await service.process()
        assert result == ProcessResult(created=0, deactivated=0)
