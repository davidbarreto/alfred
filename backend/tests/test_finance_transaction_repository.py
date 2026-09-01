import pytest
from datetime import date, datetime
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
    t.amount_eur = kwargs.get("amount_eur", None)
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


class TestGetRelated:
    async def test_returns_counterpart_when_set_and_resolvable(self):
        session = _make_session()
        counterpart = _make_txn_orm(id=2)
        session.execute.return_value = _scalar_first(counterpart)
        transaction = _make_txn_orm(id=1)
        transaction.counterpart_transaction_id = 2
        result = await TransactionRepository(session).get_related(transaction)
        assert result == counterpart

    async def test_returns_none_when_no_counterpart(self):
        session = _make_session()
        transaction = _make_txn_orm(id=1)
        transaction.counterpart_transaction_id = None
        result = await TransactionRepository(session).get_related(transaction)
        assert result is None
        session.execute.assert_not_called()

    async def test_returns_none_when_counterpart_missing(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        transaction = _make_txn_orm(id=1)
        transaction.counterpart_transaction_id = 99
        result = await TransactionRepository(session).get_related(transaction)
        assert result is None


class TestGetTransferMatchCandidates:
    def _source(self, **kwargs):
        source = _make_txn_orm(
            id=kwargs.pop("id", 1),
            amount=kwargs.pop("amount", Decimal("50.00")),
            amount_eur=kwargs.pop("amount_eur", None),
            date=kwargs.pop("date", datetime(2026, 6, 12, 10, 0)),
        )
        source.account_id = kwargs.pop("account_id", 1)
        source.currency = kwargs.pop("currency", "EUR")
        source.bank_description = kwargs.pop("bank_description", None)
        return source

    async def test_returns_matching_transactions(self):
        session = _make_session()
        candidate = _make_txn_orm(id=2)
        session.execute.return_value = _scalar_all([candidate])

        result = await TransactionRepository(session).get_transfer_match_candidates(self._source())

        assert result == [candidate]

    async def test_query_excludes_self_and_matches_opposite_amount_same_day(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        await TransactionRepository(session).get_transfer_match_candidates(self._source())

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" in sql
        assert "counterpart_transaction_id" in sql
        assert "-50.00" in sql

    async def test_query_is_not_restricted_to_transfer_type(self):
        """A leg miscategorized as expense/income on import must still be a valid
        candidate -- that's the exact case this match is meant to catch."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        await TransactionRepository(session).get_transfer_match_candidates(self._source())

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.type = 'transfer'" not in sql

    async def test_query_allows_candidate_counterpart_guessed_at_source_account(self):
        """A candidate's counterpart_account_id may already be set by an import rule's
        guess rather than a confirmed link -- if that guess already points at the source
        transaction's own account, it doesn't rule the candidate out, since that's
        consistent with this transaction being the missing counterpart."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(account_id=7)

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id IS NULL OR finance.transactions.counterpart_account_id = 7" in sql

    async def test_query_excludes_already_confirmed_linked_candidates(self):
        """A candidate that already has a confirmed counterpart_transaction_id is
        genuinely already linked (to someone else, or would be a duplicate link) --
        never offered as a match."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        await TransactionRepository(session).get_transfer_match_candidates(self._source())

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_transaction_id IS NULL" in sql

    async def test_cross_currency_matches_via_amount_eur_without_bank_description(self):
        """The whole point of the cross-currency strategy is to catch a genuine
        transfer between two different institutions (e.g. a Wise EUR debit funding a
        Banco Inter BRL credit) whose bank_description text is independently
        generated by each bank and never matches -- so when the source has an
        EUR-normalized amount, the query must not require bank_description equality
        at all."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(amount=Decimal("100.00"), amount_eur=Decimal("100.00"), bank_description=None)

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        where_clause = sql.split("WHERE", 1)[1]
        assert "bank_description" not in where_clause
        assert "amount_eur" in sql
        assert "5.00" in sql or "5.0000" in sql

    async def test_description_match_adds_amount_eur_tolerance_when_source_has_it(self):
        """Multiple same-day exchanges can share the same generic bank text (e.g.
        "Exchanged to PLN") -- when the source has a EUR-normalized amount, narrow
        candidates to those within 5% of it so an unrelated same-day exchange isn't
        offered as a false match."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(
            amount=Decimal("100.00"), amount_eur=Decimal("100.00"), bank_description="Exchanged to PLN"
        )

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "5.00" in sql or "5.0000" in sql

    async def test_falls_back_to_bank_description_when_source_lacks_amount_eur(self):
        """Without an EUR-normalized amount to compare (no FX rate on record for
        either leg), there'd be nothing to narrow a same-day, opposite-sign,
        different-currency match down beyond "some other currency's transaction
        exists" -- so fall back to requiring identical bank_description, same as a
        same-bank currency exchange (e.g. Revolut's "Exchanged to PLN")."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(amount=Decimal("100.00"), amount_eur=None, bank_description="Exchanged to PLN")

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        where_clause = sql.split("WHERE", 1)[1]
        assert "amount_eur" not in where_clause
        assert "bank_description" in sql
        assert "Exchanged to PLN" in sql

    async def test_cross_currency_strategy_requires_different_currency(self):
        """The cross-currency strategy must never fire for a same-currency pair,
        which the amount-based strategy already covers more precisely."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(currency="EUR", amount_eur=Decimal("100.00"))

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "currency !=" in sql or "!= transactions.currency" in sql or "currency <>" in sql

    async def test_query_substitutes_plan_original_amount_for_candidate_anchors(self):
        """A candidate row anchoring an installment plan (own amount zeroed -- see
        create_placeholder_for_plan) has no real amount/date of its own; the query
        must compare against InstallmentPlan.original_amount/opened_date instead."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(amount=Decimal("100.00"), date=datetime(2026, 6, 12, 10, 0))

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "installment_plans" in sql
        assert "original_amount" in sql
        assert "opened_date" in sql
        assert "-100.00" in sql

    async def test_source_itself_a_plan_anchor_substitutes_plan_amount_and_month(self):
        """Searching for matches from the placeholder/anchor row itself (own amount
        0.00) must substitute the plan's original_amount/opened_date for the search
        target, matched by month rather than exact day."""
        session = _make_session()
        plan = MagicMock()
        plan.original_amount = Decimal("100.00")
        plan.opened_date = date(2026, 6, 1)
        session.execute.side_effect = [_scalar_first(plan), _scalar_all([])]
        source = self._source(amount=Decimal("0.00"), date=datetime(2026, 6, 1, 0, 0))
        source.installment_plan_id = 5

        await TransactionRepository(session).get_transfer_match_candidates(source)

        query = session.execute.call_args_list[1].args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "-100.00" in sql
        assert "EXTRACT" in sql.upper()

    async def test_source_zero_amount_without_plan_link_is_not_treated_as_anchor(self):
        """A genuinely zero-amount transaction with no installment_plan_id must not
        trigger the plan lookup or substitution -- only one query is executed."""
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        source = self._source(amount=Decimal("0.00"))
        source.installment_plan_id = None

        await TransactionRepository(session).get_transfer_match_candidates(source)

        assert session.execute.call_count == 1


class TestSetCounterpartTransaction:
    async def test_updates_the_column(self):
        session = _make_session()

        await TransactionRepository(session).set_counterpart_transaction(1, 2)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "UPDATE finance.transactions SET counterpart_transaction_id=2" in sql
        assert "transactions.id = 1" in sql
        session.commit.assert_awaited_once()

    async def test_can_clear_the_column(self):
        session = _make_session()

        await TransactionRepository(session).set_counterpart_transaction(1, None)

        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_transaction_id=NULL" in sql


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

    async def test_search_filter_matches_description_merchant_or_bank_description(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(search="Revolut"))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "Revolut" in sql
        assert "coalesce" in sql.lower()

    async def test_unconfirmed_transfer_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(unconfirmed_transfer=True))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.type = 'transfer'" in sql
        assert "transactions.counterpart_transaction_id IS NULL" in sql

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

    async def test_default_sort_is_date_desc(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters())
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "ORDER BY FINANCE.TRANSACTIONS.DATE DESC" in sql

    async def test_sort_by_amount_asc(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(sort="amount_asc"))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "ORDER BY FINANCE.TRANSACTIONS.AMOUNT ASC" in sql

    async def test_sort_by_name_uses_coalesce(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(sort="name_asc"))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "COALESCE" in sql
        assert "ASC" in sql


class TestGetFilteredSum:
    async def test_returns_net_signed_total(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("120.00"), 5))
        total, count = await TransactionRepository(session).get_filtered_sum(TransactionFilters())
        assert total == Decimal("120.00")
        assert count == 5

    async def test_no_currency_filter_sums_amount_eur(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_filtered_sum(TransactionFilters(currency=None))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql

    async def test_explicit_currency_sums_native_amount_and_filters(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_filtered_sum(TransactionFilters(currency="USD"))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" not in sql
        assert "transactions.currency = " in sql

    async def test_applies_same_filters_as_list(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_filtered_sum(
            TransactionFilters(type="expense", category_id=3)
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "expense" in sql
        assert "transactions.category_id = " in sql


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


class TestUnlinkInstallmentPlan:
    async def test_clears_installment_plan_id_and_commits(self):
        session = _make_session()
        txn = _make_txn_orm()
        txn.installment_plan_id = 5
        session.execute.return_value = _scalar_first(txn)
        result = await TransactionRepository(session).unlink_installment_plan(1)
        assert result.installment_plan_id is None
        session.commit.assert_called_once()

    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TransactionRepository(session).unlink_installment_plan(999)
        assert result is None
        session.commit.assert_not_called()


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

    async def test_expense_query_excludes_auto_mirror_rows_from_spend(self):
        """A mirror row always has its own counterpart_transaction_id set (pointing
        back at the source leg that spawned it), so it's excluded from spend by the
        same counterpart_transaction_id check as any other confirmed transfer -- no
        separate condition needed."""
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_transaction_id" in sql

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
        """A transfer with no confirmed counterpart_transaction_id has no verified
        evidence it landed in another tracked account, so it should be included in
        "expense" totals alongside real expenses."""
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transfer" in sql
        assert "counterpart_transaction_id" in sql

    async def test_expense_query_excludes_positive_amount_transfers_from_spend(self):
        """A positive-amount untracked transfer (e.g. a Revolut top-up funded from an
        external card) is money coming in, never spend, regardless of counterpart state."""
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount" in sql and "< 0" in sql

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
        assert "counterpart_transaction_id" in sql

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


class TestGetExistingKeys:
    async def test_returns_matching_keys(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [
            (datetime(2026, 7, 3), "COMPRA 4681 Cars on Booking Amsterdam", Decimal("248.46")),
        ]
        session.execute.return_value = result
        keys = await TransactionRepository(session).get_existing_keys(5, {date(2026, 7, 3)})
        assert keys == {(date(2026, 7, 3), "COMPRA 4681 Cars on Booking Amsterdam", Decimal("248.46"))}

    async def test_empty_dates_short_circuits(self):
        session = _make_session()
        keys = await TransactionRepository(session).get_existing_keys(5, set())
        assert keys == set()
        session.execute.assert_not_called()

    async def test_filters_by_account_and_date(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_existing_keys(5, {date(2026, 7, 3)})
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "account_id" in sql
        assert "bank_description" in sql


class TestGetSpendingByAccount:
    async def test_includes_untracked_transfers(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_by_account(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_transaction_id" in sql

    async def test_global_currency_sums_amount_eur(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_by_account(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql

    async def test_returns_rows(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [(1, "Checking", Decimal("120.00"), 4)]
        session.execute.return_value = result
        rows = await TransactionRepository(session).get_spending_by_account(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert rows == [(1, "Checking", Decimal("120.00"), 4)]


class TestGetLedgerEvents:
    async def test_returns_signed_deltas_for_income_and_expense(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [
            (1, datetime(2026, 6, 1), Decimal("100.00")),
            (1, datetime(2026, 6, 2), Decimal("-30.00")),
        ]
        session.execute.return_value = result
        events = await TransactionRepository(session).get_ledger_events(date(2026, 6, 30))
        assert events == [
            (1, date(2026, 6, 1), Decimal("100.00")),
            (1, date(2026, 6, 2), Decimal("-30.00")),
        ]

    async def test_query_unions_counterpart_leg_for_transfers(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_ledger_events(date(2026, 6, 30))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "UNION ALL" in sql.upper()
        assert "counterpart_account_id" in sql

    async def test_global_currency_uses_amount_eur(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_ledger_events(date(2026, 6, 30), currency="GLOBAL")
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql

    async def test_counterpart_leg_skipped_for_rows_that_have_a_mirror(self):
        """A transfer whose counterpart account has auto_mirror_transfers enabled gets
        a real mirror Transaction row on the counterpart side (see
        TransactionService._maybe_create_mirror); that mirror already contributes its
        own credit via the unconditional source_legs half of the union, so the
        synthetic counterpart leg must be excluded via a NOT EXISTS guard to avoid
        double-crediting the counterpart account.
        """
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_ledger_events(date(2026, 6, 30))
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True})).upper()
        assert "NOT (EXISTS" in sql or "NOT EXISTS" in sql
        assert "AUTO_TRANSFER" in sql


class TestGetMirror:
    async def test_returns_mirror_row(self):
        session = _make_session()
        mirror = _make_txn_orm(id=11)
        session.execute.return_value = _scalar_first(mirror)
        result = await TransactionRepository(session).get_mirror(10)
        assert result is mirror

    async def test_returns_none_when_no_mirror_exists(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TransactionRepository(session).get_mirror(10) is None


class TestGetSpendingOverTime:
    async def test_formats_day_buckets(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [(datetime(2026, 6, 5), Decimal("30.00"))]
        session.execute.return_value = result
        rows = await TransactionRepository(session).get_spending_over_time(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
        )
        assert rows == [("2026-06-05", Decimal("30.00"))]

    async def test_formats_month_buckets(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [(datetime(2026, 6, 1), Decimal("120.00"))]
        session.execute.return_value = result
        rows = await TransactionRepository(session).get_spending_over_time(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
            group_by="month",
        )
        assert rows == [("2026-06", Decimal("120.00"))]

    async def test_does_not_cap_result_rows(self):
        """Unlike a raw transaction fetch, the aggregate query has no LIMIT --
        every bucket in the date range comes back regardless of transaction volume."""
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_over_time(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
            group_by="month",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT" not in sql.upper()
        assert "date_trunc" in sql.lower()

    async def test_global_currency_sums_amount_eur(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_over_time(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
            currency="GLOBAL",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "amount_eur" in sql
        assert "transactions.currency =" not in sql

    async def test_transaction_type_income_does_not_consider_transfers(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_spending_over_time(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
            transaction_type="income",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "counterpart_account_id" not in sql


class TestGetTransactionCounts:
    async def test_formats_month_buckets_with_counts(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [(datetime(2026, 6, 1), 5, 0, None)]
        session.execute.return_value = result
        rows = await TransactionRepository(session).get_transaction_counts(
            from_date=date(2026, 1, 1),
            to_date=date(2026, 12, 31),
            group_by="month",
        )
        assert rows == [("2026-06", 5, 0, [])]

    async def test_formats_day_buckets(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = [
            (datetime(2026, 6, 5), 2, 1, [{"id": 3, "name": "Wise EUR"}])
        ]
        session.execute.return_value = result
        rows = await TransactionRepository(session).get_transaction_counts(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
        )
        assert rows == [("2026-06-05", 2, 1, [{"id": 3, "name": "Wise EUR"}])]

    async def test_counts_regardless_of_type(self):
        """Unlike get_spending_over_time, no type/currency filtering in the WHERE
        clause -- every transaction (income, expense, transfer) contributes to the
        total count. (The CASE expression legitimately references `type` to flag
        unmatched transfers, but that's a SELECT column, not a filter.)"""
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_transaction_counts(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        # The FILTER subclause on the missing-accounts aggregate also contains a
        # "WHERE", so isolate the query's own WHERE by taking the last occurrence
        # before GROUP BY rather than the first.
        before_group_by = sql.split("GROUP BY", 1)[0]
        where_clause = before_group_by.rsplit("WHERE", 1)[1]
        assert "transactions.type =" not in where_clause
        assert "transactions.currency =" not in where_clause

    async def test_filters_by_account(self):
        session = _make_session()
        result = MagicMock()
        result.all.return_value = []
        session.execute.return_value = result
        await TransactionRepository(session).get_transaction_counts(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            group_by="day",
            account_id=7,
        )
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.account_id = 7" in sql


class TestGetEarliestTransactionDate:
    async def test_returns_date_of_earliest_transaction(self):
        session = _make_session()
        result = MagicMock()
        result.scalar.return_value = datetime(2025, 3, 4, 12, 0)
        session.execute.return_value = result
        value = await TransactionRepository(session).get_earliest_transaction_date()
        assert value == date(2025, 3, 4)

    async def test_returns_none_when_no_transactions(self):
        session = _make_session()
        result = MagicMock()
        result.scalar.return_value = None
        session.execute.return_value = result
        value = await TransactionRepository(session).get_earliest_transaction_date()
        assert value is None

    async def test_filters_by_account(self):
        session = _make_session()
        result = MagicMock()
        result.scalar.return_value = None
        session.execute.return_value = result
        await TransactionRepository(session).get_earliest_transaction_date(account_id=3)
        query = session.execute.call_args.args[0]
        sql = str(query.compile(compile_kwargs={"literal_binds": True}))
        assert "transactions.account_id = 3" in sql


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
        assert "counterpart_transaction_id" in sql

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
