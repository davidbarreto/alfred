import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import (
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionUpdate,
    TransactionFilters,
)


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    return r


def _scalar_all(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


def _one_result(values):
    r = MagicMock()
    r.one.return_value = values
    return r


def _scalar_result(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_txn_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.account_id = 1
    t.amount = kwargs.get("amount", Decimal("50"))
    t.type = kwargs.get("type", "expense")
    t.date = kwargs.get("date", "2026-06-12")
    return t


class TestGet:
    async def test_found(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        assert await TransactionRepository(session).get(1) == txn

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TransactionRepository(session).get(999) is None


class TestList:
    async def test_no_filters(self):
        session = _make_session()
        txns = [_make_txn_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(txns)
        result = await TransactionRepository(session).list(TransactionFilters())
        assert len(result) == 3

    async def test_type_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(type="income"))
        session.execute.assert_called_once()

    async def test_category_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(category_id=2))
        session.execute.assert_called_once()

    async def test_uncategorized_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(uncategorized=True))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.category_id IS NULL" in sql

    async def test_uncategorized_filter_takes_precedence_over_category_id(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(category_id=2, uncategorized=True))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.category_id IS NULL" in sql
        assert "transactions.category_id = " not in sql

    async def test_account_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(account_id=1))
        session.execute.assert_called_once()

    async def test_merchant_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(merchant="Shop"))
        session.execute.assert_called_once()

    async def test_date_range_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30)
        ))
        session.execute.assert_called_once()

    async def test_period_filter_applied_when_no_to_date(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(period="this month"))
        session.execute.assert_called_once()

    async def test_offset_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(offset=20))
        session.execute.assert_called_once()

    async def test_global_currency_does_not_filter_by_currency(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(currency="GLOBAL"))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.currency =" not in sql


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        data = TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="EUR", type="expense",
        )
        await TransactionRepository(session).create(data)
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()

    async def test_sets_amount_eur_on_created_transaction(self):
        session = _make_session()
        data = TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="USD", type="expense",
        )
        txn = await TransactionRepository(session).create(data, amount_eur=Decimal("45.00"))
        assert txn.amount_eur == Decimal("45.00")


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TransactionRepository(session).update(999, TransactionUpdate())
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_fields_and_commits(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        await TransactionRepository(session).update(1, TransactionUpdate(merchant="NewShop"))
        session.commit.assert_called_once()

    async def test_leaves_amount_eur_untouched_when_not_recomputing(self):
        session = _make_session()
        txn = _make_txn_orm()
        txn.amount_eur = Decimal("10.00")
        session.execute.return_value = _scalar_first(txn)
        result = await TransactionRepository(session).update(1, TransactionUpdate(merchant="NewShop"))
        assert result.amount_eur == Decimal("10.00")

    async def test_sets_amount_eur_when_recomputing(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        result = await TransactionRepository(session).update(
            1, TransactionUpdate(amount=Decimal("99")),
            amount_eur=Decimal("88.00"), recompute_amount_eur=True,
        )
        assert result.amount_eur == Decimal("88.00")


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TransactionRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        assert await TransactionRepository(session).delete(1) is True
        session.delete.assert_called_once_with(txn)
        session.commit.assert_called_once()


class TestGetSpendingTotal:
    async def test_returns_total_and_count(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("150.00"), 3))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert total == Decimal("150.00")
        assert count == 3

    async def test_returns_zero_when_no_results(self):
        session = _make_session()
        session.execute.return_value = _one_result((0, 0))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert total == Decimal("0")
        assert count == 0

    async def test_optional_filters_passed(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            category_id=1,
            account_id=2,
            merchant="Shop",
        )
        session.execute.assert_called_once()

    async def test_transaction_type_defaults_to_expense(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        assert "expense" in str(query.compile(compile_kwargs={"literal_binds": True}))

    async def test_transaction_type_income_override(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("500.00"), 1))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            transaction_type="income",
        )
        query = session.execute.call_args.args[0]
        assert "income" in str(query.compile(compile_kwargs={"literal_binds": True}))
        assert total == Decimal("500.00")
        assert count == 1

    async def test_expense_query_counts_untracked_transfers_as_spend(self):
        """A transfer with no counterpart_account_id never landed in another tracked
        account, so it should be included in "expense" totals alongside real expenses."""
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transfer" in sql
        assert "counterpart_account_id" in sql

    async def test_income_query_does_not_consider_transfers(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            transaction_type="income",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" not in sql

    async def test_global_currency_sums_amount_eur_across_all_currencies(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("300.00"), 5))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql
        assert total == Decimal("300.00")
        assert count == 5


class TestGetTopExpenses:
    async def test_returns_list(self):
        session = _make_session()
        txns = [_make_txn_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(txns)
        result = await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
        )
        assert len(result) == 3

    async def test_category_filter_optional(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
            category_id=1,
        )
        session.execute.assert_called_once()

    async def test_includes_untracked_transfers(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" in sql

    async def test_global_currency_orders_by_amount_eur(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql


class TestGetSpendingByCategory:
    async def test_includes_untracked_transfers(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_by_category(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" in sql

    async def test_global_currency_sums_amount_eur(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_by_category(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql


class TestGetCategorySpent:
    async def test_returns_decimal_total(self):
        session = _make_session()
        session.execute.return_value = _scalar_result(Decimal("80.00"))
        result = await TransactionRepository(session).get_category_spent(
            category_id=1,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert result == Decimal("80.00")

    async def test_includes_untracked_transfers(self):
        session = _make_session()
        session.execute.return_value = _scalar_result(Decimal("0"))
        await TransactionRepository(session).get_category_spent(
            category_id=1,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" in sql

    async def test_global_currency_sums_amount_eur(self):
        session = _make_session()
        session.execute.return_value = _scalar_result(Decimal("0"))
        await TransactionRepository(session).get_category_spent(
            category_id=1,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql


class TestMissingAmountEur:
    async def test_list_missing_amount_eur_returns_rows(self):
        session = _make_session()
        txns = [_make_txn_orm(id=i) for i in range(2)]
        session.execute.return_value = _scalar_all(txns)
        result = await TransactionRepository(session).list_missing_amount_eur(limit=10)
        assert len(result) == 2

    async def test_set_amount_eur_commits(self):
        session = _make_session()
        result_proxy = MagicMock()
        session.execute.return_value = result_proxy
        await TransactionRepository(session).set_amount_eur(1, Decimal("12.00"))
        session.commit.assert_called_once()

    async def test_count_missing_amount_eur_returns_count(self):
        session = _make_session()
        result = MagicMock()
        result.scalar_one.return_value = 7
        session.execute.return_value = result
        count = await TransactionRepository(session).count_missing_amount_eur()
        assert count == 7


class TestBulkReassignAccount:
    async def test_returns_moved_count(self):
        session = _make_session()
        result_proxy = MagicMock()
        result_proxy.rowcount = 12
        session.execute.return_value = result_proxy

        moved = await TransactionRepository(session).bulk_reassign_account(
            TransactionBulkMoveRequest(account_id=1, target_account_id=2)
        )

        assert moved == 12
        session.commit.assert_called_once()

    async def test_applies_account_and_extra_filters(self):
        session = _make_session()
        result_proxy = MagicMock()
        result_proxy.rowcount = 0
        session.execute.return_value = result_proxy

        await TransactionRepository(session).bulk_reassign_account(
            TransactionBulkMoveRequest(
                account_id=1, target_account_id=2, type="expense", category_id=3,
            )
        )

        session.execute.assert_called_once()

    async def test_statement_sets_target_account_and_clears_dedup_hash(self):
        session = _make_session()
        result_proxy = MagicMock()
        result_proxy.rowcount = 0
        session.execute.return_value = result_proxy

        await TransactionRepository(session).bulk_reassign_account(
            TransactionBulkMoveRequest(account_id=1, target_account_id=2)
        )

        stmt = session.execute.call_args[0][0]
        compiled_values = stmt._values
        # SQLAlchemy Update._values maps Column -> bound value; match by column name
        values_by_name = {col.name: val for col, val in compiled_values.items()}
        assert values_by_name["account_id"].value == 2
        assert values_by_name["deduplication_hash"].value is None
