import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.transactions.service import InvalidBulkMoveError, TransactionService
from app.features.finance.transactions.schemas import (
    AnalyticsFilters,
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
)

FIXED_TODAY = date(2026, 6, 12)


def _make_txn_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.account_id = kwargs.get("account_id", 1)
    t.date = kwargs.get("date", "2026-06-12T10:00:00")
    t.amount = kwargs.get("amount", Decimal("50.00"))
    t.currency = kwargs.get("currency", "EUR")
    t.type = kwargs.get("type", "expense")
    t.category_id = kwargs.get("category_id", None)
    t.description = kwargs.get("description", None)
    t.bank_description = kwargs.get("bank_description", None)
    t.note = kwargs.get("note", None)
    t.merchant = kwargs.get("merchant", "Shop")
    t.source = kwargs.get("source", None)
    t.counterpart_account_id = kwargs.get("counterpart_account_id", None)
    t.import_batch_id = kwargs.get("import_batch_id", None)
    t.amount_eur = kwargs.get("amount_eur", None)
    t.created_at = kwargs.get("created_at", "2026-06-12T10:00:00")
    return t


def _make_rt(type_="expense", amount=Decimal("100.00"), rule="monthly"):
    rt = MagicMock()
    rt.type = type_
    rt.amount = amount
    rt.recurrence_rule = rule
    return rt


@pytest.fixture
def service():
    svc = TransactionService.__new__(TransactionService)
    svc._repo = AsyncMock()
    svc._account_repo = AsyncMock()
    svc._fx = AsyncMock()
    svc._fx.convert_to_eur.return_value = None
    return svc


class TestGet:
    async def test_returns_transaction_read_when_found(self, service):
        service._repo.get.return_value = _make_txn_orm()
        result = await service.get(1)
        assert isinstance(result, TransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_transaction_reads(self, service):
        service._repo.list.return_value = [_make_txn_orm(id=i) for i in range(3)]
        result = await service.list(TransactionFilters())
        assert len(result) == 3
        assert all(isinstance(t, TransactionRead) for t in result)

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = TransactionFilters(type="expense", limit=10)
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)


class TestCreate:
    async def test_returns_transaction_read(self, service):
        service._repo.create.return_value = _make_txn_orm()
        result = await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="EUR", type="expense",
        ))
        assert isinstance(result, TransactionRead)

    async def test_converts_amount_and_passes_to_repo(self, service):
        service._fx.convert_to_eur.return_value = Decimal("45.00")
        service._repo.create.return_value = _make_txn_orm()

        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="USD", type="expense",
        ))

        service._fx.convert_to_eur.assert_awaited_once_with(
            Decimal("50"), "USD", date(2026, 6, 12)
        )
        assert service._repo.create.call_args.kwargs["amount_eur"] == Decimal("45.00")


class TestUpdate:
    async def test_returns_transaction_read_when_found(self, service):
        service._repo.update.return_value = _make_txn_orm(merchant="Updated")
        result = await service.update(1, TransactionUpdate(merchant="Updated"))
        assert isinstance(result, TransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, TransactionUpdate()) is None

    async def test_field_unrelated_to_fx_skips_recompute(self, service):
        service._repo.update.return_value = _make_txn_orm(merchant="Updated")

        await service.update(1, TransactionUpdate(merchant="Updated"))

        service._repo.get.assert_not_called()
        assert service._repo.update.call_args.kwargs["recompute_amount_eur"] is False

    async def test_amount_change_recomputes_amount_eur(self, service):
        from datetime import datetime as dt

        current = _make_txn_orm(amount=Decimal("50.00"), currency="USD", date=dt(2026, 6, 12))
        service._repo.get.return_value = current
        service._fx.convert_to_eur.return_value = Decimal("90.00")
        service._repo.update.return_value = _make_txn_orm(amount=Decimal("100.00"))

        await service.update(1, TransactionUpdate(amount=Decimal("100.00")))

        service._fx.convert_to_eur.assert_awaited_once_with(
            Decimal("100.00"), "USD", date(2026, 6, 12)
        )
        assert service._repo.update.call_args.kwargs["amount_eur"] == Decimal("90.00")
        assert service._repo.update.call_args.kwargs["recompute_amount_eur"] is True

    async def test_returns_none_when_fx_relevant_update_target_missing(self, service):
        service._repo.get.return_value = None
        assert await service.update(999, TransactionUpdate(amount=Decimal("10"))) is None


class TestDelete:
    async def test_passes_through_true(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_passes_through_false(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False


class TestBulkMoveAccount:
    async def test_returns_moved_count(self, service):
        service._account_repo.get.return_value = MagicMock(id=2)
        service._repo.bulk_reassign_account.return_value = 42

        moved = await service.bulk_move_account(
            TransactionBulkMoveRequest(account_id=1, target_account_id=2)
        )

        assert moved == 42
        service._repo.bulk_reassign_account.assert_awaited_once()

    async def test_rejects_same_source_and_target(self, service):
        with pytest.raises(InvalidBulkMoveError):
            await service.bulk_move_account(
                TransactionBulkMoveRequest(account_id=1, target_account_id=1)
            )
        service._repo.bulk_reassign_account.assert_not_awaited()

    async def test_rejects_missing_target_account(self, service):
        service._account_repo.get.return_value = None

        with pytest.raises(InvalidBulkMoveError):
            await service.bulk_move_account(
                TransactionBulkMoveRequest(account_id=1, target_account_id=999)
            )
        service._repo.bulk_reassign_account.assert_not_awaited()

    async def test_logs_info_with_counts(self, service, caplog):
        service._account_repo.get.return_value = MagicMock(id=2)
        service._repo.bulk_reassign_account.return_value = 7

        with caplog.at_level("INFO"):
            await service.bulk_move_account(
                TransactionBulkMoveRequest(account_id=1, target_account_id=2)
            )

        assert any(
            "bulk-moved" in m and "count=7" in m for m in caplog.messages
        )


class TestSpendingReport:
    async def test_returns_correct_response(self, service):
        service._repo.get_spending_total.return_value = (Decimal("200.00"), 4)
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.spending_report(filters)

        assert result.total == Decimal("200.00")
        assert result.currency == "EUR"
        assert result.transaction_count == 4
        assert result.from_date == date(2026, 6, 1)

    async def test_calls_repo_with_resolved_dates(self, service):
        service._repo.get_spending_total.return_value = (Decimal("0"), 0)
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        await service.spending_report(filters)

        service._repo.get_spending_total.assert_called_once_with(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            category_id=None,
            account_id=None,
            merchant=None,
            currency="EUR",
        )

    async def test_currency_passed_through(self, service):
        service._repo.get_spending_total.return_value = (Decimal("0"), 0)
        filters = AnalyticsFilters(
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30), currency="BRL"
        )

        result = await service.spending_report(filters)

        assert result.currency == "BRL"
        assert service._repo.get_spending_total.call_args.kwargs["currency"] == "BRL"


class TestIncomeReport:
    async def test_returns_correct_response(self, service):
        service._repo.get_spending_total.return_value = (Decimal("2000.00"), 1)
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.income_report(filters)

        assert result.total == Decimal("2000.00")
        assert result.currency == "EUR"
        assert result.transaction_count == 1
        assert result.from_date == date(2026, 6, 1)

    async def test_calls_repo_with_income_type(self, service):
        service._repo.get_spending_total.return_value = (Decimal("0"), 0)
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        await service.income_report(filters)

        service._repo.get_spending_total.assert_called_once_with(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            category_id=None,
            account_id=None,
            merchant=None,
            currency="EUR",
            transaction_type="income",
        )


class TestSpendingAverage:
    async def test_calculates_average_per_day(self, service):
        service._repo.get_spending_total.return_value = (Decimal("300.00"), 6)
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.spending_average(filters)

        assert result.days == 30
        assert result.total == Decimal("300.00")
        assert result.average_per_day == Decimal("10.00")

    async def test_single_day_range(self, service):
        service._repo.get_spending_total.return_value = (Decimal("50.00"), 1)
        filters = AnalyticsFilters(from_date=date(2026, 6, 12), to_date=date(2026, 6, 12))

        result = await service.spending_average(filters)

        assert result.days == 1
        assert result.average_per_day == Decimal("50.00")


class TestSpendingTop:
    async def test_returns_top_transactions(self, service):
        txns = [_make_txn_orm(id=i, amount=Decimal(str(100 - i * 10))) for i in range(3)]
        service._repo.get_top_expenses.return_value = txns
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.spending_top(filters)

        assert len(result.transactions) == 3
        assert result.top_n == 5
        assert all(isinstance(t, TransactionRead) for t in result.transactions)

    async def test_passes_top_n_to_repo(self, service):
        service._repo.get_top_expenses.return_value = []
        filters = AnalyticsFilters(
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30), top_n=10
        )
        await service.spending_top(filters)
        call_kwargs = service._repo.get_top_expenses.call_args[1]
        assert call_kwargs["top_n"] == 10


class TestBalanceForecast:
    async def test_empty_recurring_returns_zeros(self, service):
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))
        income, expenses, _ = await service.balance_forecast(filters, [])
        assert income == Decimal("0")
        assert expenses == Decimal("0")

    async def test_monthly_expense_projects_correctly(self, service):
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))
        rt = _make_rt(type_="expense", amount=Decimal("100.00"), rule="monthly")

        with patch("app.features.finance.transactions.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            income, expenses, forecast_to = await service.balance_forecast(filters, [rt])

        # days_remaining = (2026-06-30 - 2026-06-12).days = 18
        # months_remaining = 18/30 = 0.6
        # projected_expenses = 100 * 0.6 = 60
        assert expenses == Decimal("60")
        assert income == Decimal("0")
        assert forecast_to == date(2026, 6, 30)

    async def test_monthly_income_projects_correctly(self, service):
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))
        rt = _make_rt(type_="income", amount=Decimal("200.00"), rule="monthly")

        with patch("app.features.finance.transactions.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            income, expenses, _ = await service.balance_forecast(filters, [rt])

        assert income == Decimal("120")  # 200 * (18/30)
        assert expenses == Decimal("0")

    async def test_unknown_rule_contributes_zero(self, service):
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))
        rt = _make_rt(type_="expense", amount=Decimal("100.00"), rule="RRULE:FREQ=MONTHLY")

        with patch("app.features.finance.transactions.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            income, expenses, _ = await service.balance_forecast(filters, [rt])

        assert expenses == Decimal("0")

    async def test_past_forecast_to_clamps_days_to_zero(self, service):
        filters = AnalyticsFilters(from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
        rt = _make_rt(type_="expense", amount=Decimal("100.00"), rule="daily")

        with patch("app.features.finance.transactions.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
            income, expenses, _ = await service.balance_forecast(filters, [rt])

        assert expenses == Decimal("0")


class TestBackfillAmountEur:
    async def test_updates_successful_conversions_and_counts_failures(self, service):
        from datetime import datetime as dt

        pending = [
            _make_txn_orm(id=1, amount=Decimal("10.00"), currency="USD", date=dt(2026, 6, 12)),
            _make_txn_orm(id=2, amount=Decimal("20.00"), currency="XXX", date=dt(2026, 6, 12)),
        ]
        service._repo.list_missing_amount_eur.return_value = pending
        service._fx.convert_to_eur.side_effect = [Decimal("9.00"), None]
        service._repo.count_missing_amount_eur.return_value = 1

        result = await service.backfill_amount_eur(batch_size=500)

        service._repo.set_amount_eur.assert_awaited_once_with(1, Decimal("9.00"))
        assert result.updated_count == 1
        assert result.failed_count == 1
        assert result.remaining_count == 1

    async def test_no_pending_rows(self, service):
        service._repo.list_missing_amount_eur.return_value = []
        service._repo.count_missing_amount_eur.return_value = 0

        result = await service.backfill_amount_eur()

        service._repo.set_amount_eur.assert_not_called()
        assert result.updated_count == 0
        assert result.failed_count == 0
        assert result.remaining_count == 0
