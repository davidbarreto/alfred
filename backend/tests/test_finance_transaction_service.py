import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.transactions.service import (
    InvalidBulkMoveError,
    TransactionService,
    TransferMatchError,
)
from app.features.finance.transactions.schemas import (
    AnalyticsFilters,
    NetWorthFilters,
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
    TransferMatchCandidate,
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
    t.counterpart_transaction_id = kwargs.get("counterpart_transaction_id", None)
    t.import_batch_id = kwargs.get("import_batch_id", None)
    t.amount_eur = kwargs.get("amount_eur", None)
    t.balance_after = kwargs.get("balance_after", None)
    t.created_at = kwargs.get("created_at", "2026-06-12T10:00:00")
    t.installment_plan_id = kwargs.get("installment_plan_id", None)
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
    svc._repo.get_mirror.return_value = None
    svc._account_repo = AsyncMock()
    svc._account_repo.get.return_value = None
    svc._plan_repo = AsyncMock()
    svc._plan_repo.get.return_value = None
    svc._fx = AsyncMock()
    svc._fx.convert_to_eur.return_value = None
    svc._settings = AsyncMock()
    svc._settings.get_cycle_start_day.return_value = 1
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
        service._repo.list.assert_called_once_with(filters, 1)


class TestFilteredSum:
    async def test_returns_response(self, service):
        service._repo.get_filtered_sum.return_value = (Decimal("340.00"), 7)
        result = await service.filtered_sum(TransactionFilters(currency="EUR"))
        assert result.total == Decimal("340.00")
        assert result.transaction_count == 7
        assert result.currency == "EUR"

    async def test_no_currency_defaults_to_global(self, service):
        service._repo.get_filtered_sum.return_value = (Decimal("0"), 0)
        result = await service.filtered_sum(TransactionFilters())
        assert result.currency == "GLOBAL"


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


class TestCreateBalanceMaintenance:
    async def test_expense_debits_account(self, service):
        service._repo.create.return_value = _make_txn_orm(type="expense")
        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="EUR", type="expense",
        ))
        service._account_repo.adjust_balance.assert_awaited_once_with(1, Decimal("-50"))

    async def test_income_credits_account(self, service):
        service._repo.create.return_value = _make_txn_orm(type="income")
        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("2000"), currency="EUR", type="income",
        ))
        service._account_repo.adjust_balance.assert_awaited_once_with(1, Decimal("2000"))

    async def test_transfer_debits_source_and_credits_counterpart(self, service):
        service._repo.create.return_value = _make_txn_orm(type="transfer")
        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("100"), currency="EUR", type="transfer",
            counterpart_account_id=2,
        ))
        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("-100"))
        assert calls[1].args == (2, Decimal("100"))

    async def test_transfer_without_counterpart_only_debits_source(self, service):
        service._repo.create.return_value = _make_txn_orm(type="transfer")
        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("100"), currency="EUR", type="transfer",
        ))
        service._account_repo.adjust_balance.assert_awaited_once_with(1, Decimal("-100"))


class TestCreateAutoMirror:
    async def test_creates_mirror_when_counterpart_has_auto_mirror_enabled(self, service):
        source = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"),
            counterpart_account_id=2, currency="EUR",
        )
        mirror = _make_txn_orm(id=11, account_id=2, type="transfer", amount=Decimal("-100.00"))
        service._repo.create.side_effect = [source, mirror]
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=True)

        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("100"), currency="EUR", type="transfer",
            counterpart_account_id=2,
        ))

        assert service._repo.create.await_count == 2
        mirror_data = service._repo.create.await_args_list[1].args[0]
        assert mirror_data.account_id == 2
        assert mirror_data.amount == Decimal("-100.00")
        assert mirror_data.counterpart_account_id is None
        assert mirror_data.counterpart_transaction_id == 10
        service._repo.set_counterpart_transaction.assert_awaited_once_with(10, 11)

    async def test_phantom_counterpart_credit_still_applied_alongside_mirror(self, service):
        source = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2
        )
        mirror = _make_txn_orm(id=11, account_id=2, type="transfer", amount=Decimal("-100.00"))
        service._repo.create.side_effect = [source, mirror]
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=True)

        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("100"), currency="EUR", type="transfer",
            counterpart_account_id=2,
        ))

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("-100"))
        assert calls[1].args == (2, Decimal("100"))
        assert len(calls) == 2  # mirror creation itself never calls adjust_balance

    async def test_no_mirror_when_counterpart_flag_disabled(self, service):
        service._repo.create.return_value = _make_txn_orm(id=10, type="transfer")
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=False)

        await service.create(TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("100"), currency="EUR", type="transfer",
            counterpart_account_id=2,
        ))

        assert service._repo.create.await_count == 1


class TestUpdate:
    async def test_returns_transaction_read_when_found(self, service):
        service._repo.update.return_value = _make_txn_orm(merchant="Updated")
        result = await service.update(1, TransactionUpdate(merchant="Updated"))
        assert isinstance(result, TransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, TransactionUpdate()) is None

    async def test_field_unrelated_to_fx_skips_recompute(self, service):
        service._repo.get.return_value = _make_txn_orm()
        service._repo.update.return_value = _make_txn_orm(merchant="Updated")

        await service.update(1, TransactionUpdate(merchant="Updated"))

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


class TestSyncCounterpartLink:
    async def test_amount_change_on_confirmed_leg_clears_link_on_both_sides(self, service):
        from datetime import datetime as dt

        current = _make_txn_orm(
            id=1, type="transfer", counterpart_account_id=2, counterpart_transaction_id=2,
            date=dt(2026, 6, 12),
        )
        service._repo.get.return_value = current
        service._repo.update.return_value = _make_txn_orm(
            id=1, type="transfer", amount=Decimal("999.00"),
            counterpart_account_id=2, counterpart_transaction_id=2,
        )

        await service.update(1, TransactionUpdate(amount=Decimal("999.00")))

        service._repo.set_counterpart_transaction.assert_any_await(1, None)
        service._repo.set_counterpart_transaction.assert_any_await(2, None)

    async def test_counterpart_account_change_on_confirmed_leg_clears_link(self, service):
        current = _make_txn_orm(
            id=1, type="transfer", counterpart_account_id=2, counterpart_transaction_id=2,
        )
        service._repo.get.return_value = current
        service._repo.update.return_value = _make_txn_orm(
            id=1, type="transfer", counterpart_account_id=3, counterpart_transaction_id=2,
        )

        await service.update(1, TransactionUpdate(counterpart_account_id=3))

        service._repo.set_counterpart_transaction.assert_any_await(1, None)
        service._repo.set_counterpart_transaction.assert_any_await(2, None)

    async def test_type_change_away_from_transfer_clears_link(self, service):
        current = _make_txn_orm(
            id=1, type="transfer", counterpart_account_id=2, counterpart_transaction_id=2,
        )
        service._repo.get.return_value = current
        service._repo.update.return_value = _make_txn_orm(
            id=1, type="expense", counterpart_account_id=2, counterpart_transaction_id=2,
        )

        await service.update(1, TransactionUpdate(type="expense"))

        service._repo.set_counterpart_transaction.assert_any_await(1, None)
        service._repo.set_counterpart_transaction.assert_any_await(2, None)

    async def test_unrelated_field_change_leaves_confirmed_link_intact(self, service):
        current = _make_txn_orm(
            id=1, type="transfer", counterpart_account_id=2, counterpart_transaction_id=2,
        )
        service._repo.get.return_value = current
        service._repo.update.return_value = _make_txn_orm(
            id=1, type="transfer", merchant="Renamed",
            counterpart_account_id=2, counterpart_transaction_id=2,
        )

        await service.update(1, TransactionUpdate(merchant="Renamed"))

        service._repo.set_counterpart_transaction.assert_not_awaited()

    async def test_no_prior_link_never_calls_unlink(self, service):
        from datetime import datetime as dt

        current = _make_txn_orm(id=1, type="expense", date=dt(2026, 6, 12))
        service._repo.get.return_value = current
        service._repo.update.return_value = _make_txn_orm(id=1, type="expense", amount=Decimal("5.00"))

        await service.update(1, TransactionUpdate(amount=Decimal("5.00")))

        service._repo.set_counterpart_transaction.assert_not_awaited()


class TestUpdateBalanceMaintenance:
    async def test_amount_change_reverses_old_and_applies_new(self, service):
        from datetime import datetime as dt

        old = _make_txn_orm(account_id=1, type="expense", amount=Decimal("50.00"), date=dt(2026, 6, 12))
        new = _make_txn_orm(account_id=1, type="expense", amount=Decimal("80.00"))
        service._repo.get.return_value = old
        service._repo.update.return_value = new

        await service.update(1, TransactionUpdate(amount=Decimal("80.00")))

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("50.00"))
        assert calls[1].args == (1, Decimal("-80.00"))

    async def test_account_reassignment_moves_the_balance_effect(self, service):
        old = _make_txn_orm(account_id=1, type="expense", amount=Decimal("50.00"))
        new = _make_txn_orm(account_id=2, type="expense", amount=Decimal("50.00"))
        service._repo.get.return_value = old
        service._repo.update.return_value = new

        await service.update(1, TransactionUpdate(account_id=2))

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("50.00"))
        assert calls[1].args == (2, Decimal("-50.00"))

    async def test_type_change_from_expense_to_income(self, service):
        old = _make_txn_orm(account_id=1, type="expense", amount=Decimal("50.00"))
        new = _make_txn_orm(account_id=1, type="income", amount=Decimal("50.00"))
        service._repo.get.return_value = old
        service._repo.update.return_value = new

        await service.update(1, TransactionUpdate(type="income"))

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("50.00"))
        assert calls[1].args == (1, Decimal("50.00"))

    async def test_not_found_does_not_touch_balance(self, service):
        service._repo.get.return_value = None
        await service.update(999, TransactionUpdate(merchant="X"))
        service._account_repo.adjust_balance.assert_not_awaited()

    async def test_reconciles_correctly_when_repo_mutates_the_same_object_in_place(self, service):
        """Regression test for the SQLAlchemy identity-map aliasing bug: the real
        TransactionRepository.get() and .update() share a session identity map, so
        both calls return the *same* ORM object, and .update() mutates it via setattr
        rather than returning a distinct copy. If TransactionService.update() diffs
        against that live object instead of a pre-mutation snapshot, "old" silently
        reflects the post-update state too, and the balance reconciliation nets to
        zero instead of reversing the old effect and applying the new one.
        """
        from datetime import datetime as dt

        shared = _make_txn_orm(account_id=1, type="expense", amount=Decimal("10.00"), date=dt(2026, 6, 12))
        service._repo.get.return_value = shared

        async def mutating_update(transaction_id, data, amount_eur=None, recompute_amount_eur=False):
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(shared, field, value)
            return shared

        service._repo.update.side_effect = mutating_update

        await service.update(1, TransactionUpdate(amount=Decimal("40.00")))

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("10.00"))
        assert calls[1].args == (1, Decimal("-40.00"))


class TestUpdateAutoMirror:
    async def test_amount_change_syncs_existing_mirror(self, service):
        from datetime import datetime as dt

        old = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2,
            date=dt(2026, 6, 12),
        )
        new = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("150.00"), counterpart_account_id=2
        )
        service._repo.get.return_value = old
        service._repo.update.return_value = new
        mirror = _make_txn_orm(
            id=11, account_id=2, type="transfer", amount=Decimal("-100.00"), source="auto_transfer",
        )
        service._repo.get_mirror.return_value = mirror
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=True)

        await service.update(10, TransactionUpdate(amount=Decimal("150.00")))

        mirror_call = service._repo.update.await_args_list[-1]
        assert mirror_call.args[0] == 11
        assert mirror_call.args[1].amount == Decimal("-150.00")

    async def test_disabling_mirroring_removes_the_mirror(self, service):
        from datetime import datetime as dt

        old = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2,
            date=dt(2026, 6, 12),
        )
        new = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2
        )
        service._repo.get.return_value = old
        service._repo.update.return_value = new
        mirror = _make_txn_orm(id=11, account_id=2, source="auto_transfer")
        service._repo.get_mirror.return_value = mirror
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=False)

        await service.update(10, TransactionUpdate(amount=Decimal("100.00")))

        service._repo.delete.assert_awaited_once_with(11)

    async def test_editing_mirror_row_directly_skips_reconciliation_and_sync(self, service):
        from datetime import datetime as dt

        old = _make_txn_orm(
            id=11, account_id=2, type="transfer", amount=Decimal("-100.00"), source="auto_transfer",
            date=dt(2026, 6, 12),
        )
        new = _make_txn_orm(
            id=11, account_id=2, type="transfer", amount=Decimal("-150.00"), source="auto_transfer",
        )
        service._repo.get.return_value = old
        service._repo.update.return_value = new

        await service.update(11, TransactionUpdate(amount=Decimal("-150.00")))

        service._repo.get_mirror.assert_not_awaited()
        service._account_repo.adjust_balance.assert_not_awaited()


class TestDelete:
    async def test_passes_through_true(self, service):
        service._repo.get.return_value = _make_txn_orm()
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_passes_through_false(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False

    async def test_not_found_returns_false_without_touching_balance(self, service):
        service._repo.get.return_value = None
        assert await service.delete(999) is False
        service._account_repo.adjust_balance.assert_not_awaited()


class TestDeleteBalanceMaintenance:
    async def test_expense_deletion_credits_back_the_account(self, service):
        service._repo.get.return_value = _make_txn_orm(
            account_id=1, type="expense", amount=Decimal("50.00")
        )
        service._repo.delete.return_value = True

        await service.delete(1)

        service._account_repo.adjust_balance.assert_awaited_once_with(1, Decimal("50.00"))

    async def test_transfer_deletion_reverses_both_legs(self, service):
        service._repo.get.return_value = _make_txn_orm(
            account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2
        )
        service._repo.delete.return_value = True

        await service.delete(1)

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("100.00"))
        assert calls[1].args == (2, Decimal("-100.00"))


class TestDeleteAutoMirror:
    async def test_deleting_a_mirror_row_directly_is_balance_neutral(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=11, account_id=2, type="transfer", amount=Decimal("-100.00"),
            counterpart_account_id=None, source="auto_transfer",
        )
        service._repo.delete.return_value = True

        await service.delete(11)

        service._account_repo.adjust_balance.assert_not_awaited()

    async def test_deleting_the_source_leg_still_reverses_normally(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"), counterpart_account_id=2
        )
        service._repo.delete.return_value = True

        await service.delete(10)

        calls = service._account_repo.adjust_balance.await_args_list
        assert calls[0].args == (1, Decimal("100.00"))
        assert calls[1].args == (2, Decimal("-100.00"))


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


class TestGetTransferMatchCandidates:
    async def test_returns_candidates_for_unmatched_transfer(self, service):
        service._repo.get.return_value = _make_txn_orm(type="transfer", counterpart_account_id=None)
        service._repo.get_transfer_match_candidates.return_value = [
            _make_txn_orm(id=2, account_id=2, type="transfer", amount=Decimal("-50.00"))
        ]
        result = await service.get_transfer_match_candidates(1)
        assert len(result) == 1
        assert isinstance(result[0], TransferMatchCandidate)
        assert result[0].plan_original_amount is None

    async def test_returns_empty_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get_transfer_match_candidates(999) == []

    async def test_returns_candidates_for_non_transfer_type(self, service):
        """A miscategorized transfer (imported as expense/income, no tracked destination
        account) can still be matched -- linking will convert its type to transfer."""
        service._repo.get.return_value = _make_txn_orm(type="expense", counterpart_account_id=None)
        service._repo.get_transfer_match_candidates.return_value = [
            _make_txn_orm(id=2, account_id=2, type="transfer", amount=Decimal("-50.00"))
        ]
        result = await service.get_transfer_match_candidates(1)
        assert len(result) == 1

    async def test_searches_even_when_counterpart_account_already_set(self, service):
        """counterpart_account_id may only be a rule-guessed destination account with no
        reciprocal row ever confirmed -- still worth searching for a real match."""
        service._repo.get.return_value = _make_txn_orm(type="transfer", counterpart_account_id=3)
        service._repo.get_transfer_match_candidates.return_value = [
            _make_txn_orm(id=2, account_id=2, type="expense", amount=Decimal("-50.00"))
        ]
        result = await service.get_transfer_match_candidates(1)
        assert len(result) == 1

    async def test_returns_empty_for_generated_mirror_row(self, service):
        service._repo.get.return_value = _make_txn_orm(
            type="transfer", source="auto_transfer"
        )
        assert await service.get_transfer_match_candidates(1) == []
        service._repo.get_transfer_match_candidates.assert_not_awaited()

    async def test_surfaces_plan_original_amount_for_installment_plan_anchor_candidate(self, service):
        """A candidate anchoring an installment plan has its own amount zeroed --
        surface the plan's original_amount separately so the UI doesn't show a
        misleading 0.00 as the match amount."""
        service._repo.get.return_value = _make_txn_orm(type="income", counterpart_account_id=None)
        service._repo.get_transfer_match_candidates.return_value = [
            _make_txn_orm(
                id=2, account_id=2, type="expense", amount=Decimal("0.00"), installment_plan_id=7,
            )
        ]
        plan = MagicMock()
        plan.original_amount = Decimal("-100.00")
        service._plan_repo.get.return_value = plan

        result = await service.get_transfer_match_candidates(1)

        assert result[0].plan_original_amount == Decimal("-100.00")
        service._plan_repo.get.assert_any_await(7)

    async def test_plan_original_amount_stays_none_when_plan_has_no_original_amount(self, service):
        """A manually-created plan (Cetelem/Nubank) has no lump sum at all -- an anchor
        can't exist for it, but guard the lookup regardless."""
        service._repo.get.return_value = _make_txn_orm(type="income", counterpart_account_id=None)
        service._repo.get_transfer_match_candidates.return_value = [
            _make_txn_orm(
                id=2, account_id=2, type="expense", amount=Decimal("0.00"), installment_plan_id=7,
            )
        ]
        plan = MagicMock()
        plan.original_amount = None
        service._plan_repo.get.return_value = plan

        result = await service.get_transfer_match_candidates(1)

        assert result[0].plan_original_amount is None


class TestSearchLinkCandidates:
    async def test_returns_matching_transactions(self, service):
        service._repo.list.return_value = [
            _make_txn_orm(id=2, account_id=2, type="expense", amount=Decimal("-100.00"))
        ]

        result = await service.search_link_candidates(1, "Revolut")

        assert len(result) == 1
        assert isinstance(result[0], TransferMatchCandidate)
        args, kwargs = service._repo.list.call_args
        assert args[0].search == "Revolut"

    async def test_returns_empty_for_blank_query(self, service):
        result = await service.search_link_candidates(1, "   ")
        assert result == []
        service._repo.list.assert_not_awaited()

    async def test_excludes_the_searching_transaction_itself(self, service):
        service._repo.list.return_value = [
            _make_txn_orm(id=1, account_id=1, type="expense", amount=Decimal("-100.00")),
            _make_txn_orm(id=2, account_id=2, type="expense", amount=Decimal("-100.00")),
        ]

        result = await service.search_link_candidates(1, "Revolut")

        assert [c.id for c in result] == [2]

    async def test_surfaces_plan_original_amount_for_matched_anchor(self, service):
        service._repo.list.return_value = [
            _make_txn_orm(
                id=2, account_id=2, type="expense", amount=Decimal("0.00"), installment_plan_id=7,
            )
        ]
        plan = MagicMock()
        plan.original_amount = Decimal("-100.00")
        service._plan_repo.get.return_value = plan

        result = await service.search_link_candidates(1, "Revolut")

        assert result[0].plan_original_amount == Decimal("-100.00")


class TestLinkTransfer:
    async def test_links_both_legs(self, service):
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(id=1, account_id=1, type="transfer", amount=Decimal("50.00"), date=same_date)
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-50.00"), date=same_date
        )
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            1,
            TransactionUpdate(type="transfer", counterpart_account_id=2, counterpart_transaction_id=2),
            amount_eur=None, recompute_amount_eur=False,
        )
        service._repo.update.assert_any_await(
            2,
            TransactionUpdate(type="transfer", counterpart_account_id=1, counterpart_transaction_id=1),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_persists_link_when_repo_mutates_the_same_object_in_place(self, service):
        """Regression test for the identity-map aliasing bug (see
        TestUpdateBalanceMaintenance.test_reconciles_correctly_when_repo_mutates_the_same_object_in_place)
        as it manifests in link_transfer specifically: linking two legs calls update()
        twice, each setting type/counterpart_account_id/counterpart_transaction_id
        together -- exactly the fields _sync_counterpart_link treats as invalidating a
        prior link. If "old" aliased the just-mutated object, _sync_counterpart_link
        would see a spuriously already-set counterpart_transaction_id and immediately
        null out the link this very call just established.
        """
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(id=1, account_id=1, type="transfer", amount=Decimal("50.00"), date=same_date)
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-50.00"), date=same_date
        )
        store = {1: txn, 2: counterpart}

        async def fake_get(transaction_id):
            return store.get(transaction_id)

        async def fake_update(transaction_id, data, amount_eur=None, recompute_amount_eur=False):
            obj = store[transaction_id]
            for field, value in data.model_dump(exclude_unset=True).items():
                setattr(obj, field, value)
            return obj

        service._repo.get.side_effect = fake_get
        service._repo.update.side_effect = fake_update

        await service.link_transfer(1, 2)

        assert txn.counterpart_transaction_id == 2
        assert counterpart.counterpart_transaction_id == 1
        service._repo.set_counterpart_transaction.assert_not_awaited()

    async def test_rejects_linking_to_self(self, service):
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 1)
        service._repo.get.assert_not_awaited()

    async def test_rejects_when_transaction_not_found(self, service):
        service._repo.get.side_effect = [None, _make_txn_orm(id=2)]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_converts_non_transfer_leg_to_transfer_on_link(self, service):
        """A leg imported as expense/income (a miscategorized transfer with no tracked
        destination account) is converted to type='transfer' when linked, so it's
        consistently excluded from spend/income totals afterward."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="expense", amount=Decimal("50.00"), date=same_date
        )
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-50.00"), date=same_date
        )
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            1,
            TransactionUpdate(type="transfer", counterpart_account_id=2, counterpart_transaction_id=2),
            amount_eur=None, recompute_amount_eur=False,
        )
        service._repo.update.assert_any_await(
            2,
            TransactionUpdate(type="transfer", counterpart_account_id=1, counterpart_transaction_id=1),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_rejects_already_linked_counterpart(self, service):
        service._repo.get.side_effect = [
            _make_txn_orm(id=1, account_id=1, type="transfer"),
            _make_txn_orm(id=2, account_id=2, type="transfer", counterpart_account_id=9),
        ]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_rejects_generated_mirror_row(self, service):
        service._repo.get.side_effect = [
            _make_txn_orm(id=1, account_id=1, type="transfer", source="auto_transfer"),
            _make_txn_orm(id=2, account_id=2, type="transfer"),
        ]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_allows_source_with_rule_guessed_counterpart_account(self, service):
        """A source leg's counterpart_account_id may already be set by an import rule's
        guessed destination account, with no reciprocal row ever confirmed -- linking to
        a genuine match should still succeed and overwrite the guess."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("50.00"), date=same_date,
            counterpart_account_id=9,
        )
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-50.00"), date=same_date
        )
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            1,
            TransactionUpdate(type="transfer", counterpart_account_id=2, counterpart_transaction_id=2),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_allows_counterpart_with_rule_guessed_account_matching_source(self, service):
        """A counterpart leg's counterpart_account_id may already be set by an import
        rule's guessed destination account -- if that guess already points back at the
        source transaction's own account, it's consistent with this being a genuine (if
        previously unconfirmed) link, so it should not block linking."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("50.00"), date=same_date,
        )
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-50.00"), date=same_date,
            counterpart_account_id=1,
        )
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            2,
            TransactionUpdate(type="transfer", counterpart_account_id=1, counterpart_transaction_id=1),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_rejects_same_account(self, service):
        service._repo.get.side_effect = [
            _make_txn_orm(id=1, account_id=1, type="transfer"),
            _make_txn_orm(id=2, account_id=1, type="transfer"),
        ]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_rejects_mismatched_amount(self, service):
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        service._repo.get.side_effect = [
            _make_txn_orm(id=1, account_id=1, type="transfer", amount=Decimal("50.00"), date=same_date),
            _make_txn_orm(id=2, account_id=2, type="transfer", amount=Decimal("-40.00"), date=same_date),
        ]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_rejects_mismatched_date(self, service):
        from datetime import datetime
        service._repo.get.side_effect = [
            _make_txn_orm(
                id=1, account_id=1, type="transfer", amount=Decimal("50.00"),
                date=datetime(2026, 6, 12),
            ),
            _make_txn_orm(
                id=2, account_id=2, type="transfer", amount=Decimal("-50.00"),
                date=datetime(2026, 6, 13),
            ),
        ]
        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_links_currency_exchange_legs_via_matching_bank_description(self, service):
        """Different currencies and an FX-converted (not exactly opposite) amount --
        only a shared bank_description (as Revolut gives both legs of one Exchange row)
        can link these, mirroring get_transfer_match_candidates' second strategy."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("100.00"), currency="EUR",
            date=same_date,
        )
        txn.bank_description = "Exchanged to PLN"
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-434.09"), currency="PLN",
            date=same_date,
        )
        counterpart.bank_description = "Exchanged to PLN"
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            1,
            TransactionUpdate(type="transfer", counterpart_account_id=2, counterpart_transaction_id=2),
            amount_eur=None, recompute_amount_eur=False,
        )
        service._repo.update.assert_any_await(
            2,
            TransactionUpdate(type="transfer", counterpart_account_id=1, counterpart_transaction_id=1),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_links_cross_currency_transfer_via_amount_eur_without_matching_description(self, service):
        """A genuine transfer between two different institutions (e.g. a Wise EUR
        debit funding a Banco Inter BRL credit) has independently-generated
        bank_description text on each leg that never matches -- when both legs have
        an EUR-normalized amount within 5% of each other, the link must still
        succeed without requiring bank_description equality."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("-100.00"), currency="EUR",
            date=same_date, amount_eur=Decimal("100.00"),
        )
        txn.bank_description = "David Ferreira"
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("560.00"), currency="BRL",
            date=same_date, amount_eur=Decimal("103.00"),
        )
        counterpart.bank_description = "Transferencia Recebida - Wise"
        service._repo.get.side_effect = [txn, counterpart, txn, counterpart]
        service._repo.update.return_value = txn

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._repo.update.assert_any_await(
            1,
            TransactionUpdate(type="transfer", counterpart_account_id=2, counterpart_transaction_id=2),
            amount_eur=None, recompute_amount_eur=False,
        )

    async def test_rejects_cross_currency_transfer_when_amount_eur_diverges_too_much(self, service):
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        service._repo.get.side_effect = [
            _make_txn_orm(
                id=1, account_id=1, type="transfer", amount=Decimal("-100.00"), currency="EUR",
                date=same_date, amount_eur=Decimal("100.00"),
            ),
            _make_txn_orm(
                id=2, account_id=2, type="transfer", amount=Decimal("560.00"), currency="BRL",
                date=same_date, amount_eur=Decimal("140.00"),
            ),
        ]

        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_rejects_currency_exchange_with_different_descriptions(self, service):
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("100.00"), currency="EUR",
            date=same_date,
        )
        txn.bank_description = "Exchanged to PLN"
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-434.09"), currency="PLN",
            date=same_date,
        )
        counterpart.bank_description = "Unrelated transfer"
        service._repo.get.side_effect = [txn, counterpart]

        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_rejects_same_currency_matching_description(self, service):
        """The description-based strategy is for currency exchanges specifically --
        a same-currency pair with a matching description must still be rejected here,
        since it isn't a genuine exchange (and the amount-based strategy already
        covers same-currency pairs more precisely)."""
        from datetime import datetime
        same_date = datetime(2026, 6, 12)
        txn = _make_txn_orm(
            id=1, account_id=1, type="transfer", amount=Decimal("100.00"), currency="EUR",
            date=same_date,
        )
        txn.bank_description = "Some transfer"
        counterpart = _make_txn_orm(
            id=2, account_id=2, type="transfer", amount=Decimal("-40.00"), currency="EUR",
            date=same_date,
        )
        counterpart.bank_description = "Some transfer"
        service._repo.get.side_effect = [txn, counterpart]

        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)

    async def test_links_against_installment_plan_anchor_using_original_amount_and_month(self, service):
        """A placeholder/superseded-original row anchoring an installment plan (own
        amount zeroed -- see TransactionRepository.create_placeholder_for_plan) has
        no real amount/date of its own to validate against; the plan's
        original_amount/opened_date must be substituted, matched by month rather
        than exact day since opened_date is only an import period boundary."""
        from datetime import datetime
        txn = _make_txn_orm(
            id=1, account_id=1, type="income", amount=Decimal("100.00"), currency="EUR",
            date=datetime(2026, 6, 15),
        )
        anchor = _make_txn_orm(
            id=2, account_id=2, type="expense", amount=Decimal("0.00"), currency="EUR",
            date=datetime(2026, 6, 1), installment_plan_id=7,
        )
        service._repo.get.side_effect = [txn, anchor, txn, anchor]
        service._repo.update.return_value = txn
        plan = MagicMock()
        plan.original_amount = Decimal("-100.00")
        plan.opened_date = date(2026, 6, 1)
        service._plan_repo.get.return_value = plan

        result = await service.link_transfer(1, 2)

        assert isinstance(result, TransactionRead)
        service._plan_repo.get.assert_any_await(7)

    async def test_rejects_plan_anchor_match_outside_opened_month(self, service):
        from datetime import datetime
        txn = _make_txn_orm(
            id=1, account_id=1, type="income", amount=Decimal("100.00"), currency="EUR",
            date=datetime(2026, 7, 15),
        )
        anchor = _make_txn_orm(
            id=2, account_id=2, type="expense", amount=Decimal("0.00"), currency="EUR",
            date=datetime(2026, 6, 1), installment_plan_id=7,
        )
        service._repo.get.side_effect = [txn, anchor]
        plan = MagicMock()
        plan.original_amount = Decimal("-100.00")
        plan.opened_date = date(2026, 6, 1)
        service._plan_repo.get.return_value = plan

        with pytest.raises(TransferMatchError):
            await service.link_transfer(1, 2)


class TestAutoCreateTransferMirror:
    async def test_creates_mirror_and_returns_updated_transaction(self, service):
        source = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"),
            counterpart_account_id=2, currency="EUR",
        )
        mirror = _make_txn_orm(id=11, account_id=2, type="transfer", amount=Decimal("-100.00"))
        updated_source = _make_txn_orm(
            id=10, account_id=1, type="transfer", amount=Decimal("100.00"),
            counterpart_account_id=2, counterpart_transaction_id=11, currency="EUR",
        )
        service._repo.get.side_effect = [source, updated_source]
        service._repo.create.return_value = mirror
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=True)

        result = await service.auto_create_transfer_mirror(10)

        assert result.id == 10
        assert result.counterpart_transaction_id == 11
        service._repo.set_counterpart_transaction.assert_awaited_once_with(10, 11)

    async def test_rejects_when_transaction_not_found(self, service):
        service._repo.get.return_value = None
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_generated_mirror_row(self, service):
        service._repo.get.return_value = _make_txn_orm(id=10, source="auto_transfer")
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_already_linked(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, type="transfer", counterpart_transaction_id=99
        )
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_non_transfer_type(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, type="expense", counterpart_account_id=2
        )
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_missing_counterpart_account(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, type="transfer", counterpart_account_id=None
        )
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_when_counterpart_account_does_not_auto_mirror(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, type="transfer", counterpart_account_id=2
        )
        service._account_repo.get.return_value = MagicMock(auto_mirror_transfers=False)
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)

    async def test_rejects_when_counterpart_account_not_found(self, service):
        service._repo.get.return_value = _make_txn_orm(
            id=10, type="transfer", counterpart_account_id=2
        )
        service._account_repo.get.return_value = None
        with pytest.raises(TransferMatchError):
            await service.auto_create_transfer_mirror(10)


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


class TestSpendingOverTime:
    async def test_returns_items_from_repo(self, service):
        service._repo.get_spending_over_time.return_value = [
            ("2026-06-01", Decimal("30.00")),
            ("2026-06-02", Decimal("15.00")),
        ]
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.spending_over_time(filters, group_by="day")

        assert [i.period for i in result.items] == ["2026-06-01", "2026-06-02"]
        assert result.group_by == "day"
        assert result.from_date == date(2026, 6, 1)
        assert result.to_date == date(2026, 6, 30)

    async def test_passes_group_by_to_repo(self, service):
        service._repo.get_spending_over_time.return_value = []
        filters = AnalyticsFilters(from_date=date(2026, 1, 1), to_date=date(2026, 12, 31))

        await service.spending_over_time(filters, group_by="month")

        call_kwargs = service._repo.get_spending_over_time.call_args[1]
        assert call_kwargs["group_by"] == "month"


class TestTransactionCoverage:
    async def test_returns_items_with_unmatched_transfer_counts(self, service):
        service._repo.get_transaction_counts.return_value = [
            ("2026-05", 10, 0, []),
            ("2026-06", 4, 2, [{"id": 3, "name": "Wise EUR"}]),
        ]

        result = await service.transaction_coverage(
            account_id=1, group_by="month", from_date=date(2026, 5, 1), to_date=date(2026, 6, 30)
        )

        assert [i.period for i in result.items] == ["2026-05", "2026-06"]
        assert result.items[1].count == 4
        assert result.items[1].unmatched_transfer_count == 2
        assert result.items[1].unmatched_transfer_accounts[0].id == 3
        assert result.items[1].unmatched_transfer_accounts[0].name == "Wise EUR"
        assert result.items[0].unmatched_transfer_accounts == []
        assert result.from_date == date(2026, 5, 1)
        assert result.to_date == date(2026, 6, 30)
        assert result.account_id == 1

    async def test_defaults_from_date_to_earliest_transaction(self, service):
        service._repo.get_earliest_transaction_date.return_value = date(2025, 1, 15)
        service._repo.get_transaction_counts.return_value = []

        result = await service.transaction_coverage(
            account_id=2, group_by="month", from_date=None, to_date=date(2026, 6, 30)
        )

        service._repo.get_earliest_transaction_date.assert_awaited_once_with(2)
        assert result.from_date == date(2025, 1, 15)
        call_kwargs = service._repo.get_transaction_counts.call_args[1]
        assert call_kwargs["from_date"] == date(2025, 1, 15)

    async def test_defaults_to_date_to_today(self, service):
        service._repo.get_earliest_transaction_date.return_value = date(2025, 1, 1)
        service._repo.get_transaction_counts.return_value = []

        result = await service.transaction_coverage(
            account_id=None, group_by="month", from_date=date(2025, 1, 1), to_date=None
        )

        assert result.to_date == date.today()

    async def test_no_transactions_falls_back_from_date_to_resolved_to_date(self, service):
        """An account with no transactions at all has no earliest date to anchor
        on -- the range collapses to a single empty day rather than erroring."""
        service._repo.get_earliest_transaction_date.return_value = None
        service._repo.get_transaction_counts.return_value = []

        result = await service.transaction_coverage(
            account_id=5, group_by="month", from_date=None, to_date=date(2026, 6, 30)
        )

        assert result.from_date == date(2026, 6, 30)


class TestSpendingByAccount:
    async def test_returns_items(self, service):
        service._repo.get_spending_by_account.return_value = [
            (1, "Checking", Decimal("120.00"), 3)
        ]
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.spending_by_account(filters)

        assert result.items[0].account_id == 1
        assert result.items[0].account_name == "Checking"
        assert result.items[0].total == Decimal("120.00")
        assert result.items[0].transaction_count == 3


class TestIncomeVsExpenseOverTime:
    async def test_merges_income_and_expense_by_period(self, service):
        service._repo.get_spending_over_time.side_effect = [
            [("2026-06-01", Decimal("30.00"))],
            [("2026-06-01", Decimal("100.00")), ("2026-06-02", Decimal("50.00"))],
        ]
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        result = await service.income_vs_expense_over_time(filters, group_by="day")

        items = {i.period: i for i in result.items}
        assert items["2026-06-01"].income == Decimal("100.00")
        assert items["2026-06-01"].expense == Decimal("30.00")
        assert items["2026-06-02"].income == Decimal("50.00")
        assert items["2026-06-02"].expense == Decimal("0")

    async def test_calls_repo_with_expense_then_income_type(self, service):
        service._repo.get_spending_over_time.return_value = []
        filters = AnalyticsFilters(from_date=date(2026, 6, 1), to_date=date(2026, 6, 30))

        await service.income_vs_expense_over_time(filters, group_by="day")

        call_types = [
            c.kwargs["transaction_type"] for c in service._repo.get_spending_over_time.call_args_list
        ]
        assert call_types == ["expense", "income"]


class TestNetWorthHistory:
    async def test_computes_running_total_from_ledger(self, service):
        service._account_repo.list.return_value = []
        service._repo.get_ledger_events.return_value = [
            (1, date(2026, 5, 1), Decimal("1000.00")),
            (1, date(2026, 6, 1), Decimal("-200.00")),
        ]
        filters = NetWorthFilters(to_date=date(2026, 6, 30), currency="EUR")

        result = await service.net_worth_history(filters, group_by="month")

        totals = {i.period: i.total for i in result.items}
        assert totals["2026-05"] == Decimal("1000.00")
        assert totals["2026-06"] == Decimal("800.00")

    async def test_includes_opening_balance_anchor(self, service):
        account = MagicMock(id=1, opening_balance=Decimal("500.00"), opening_balance_date=date(2026, 1, 1))
        service._account_repo.list.return_value = [account]
        service._repo.get_ledger_events.return_value = [
            (1, date(2026, 2, 1), Decimal("50.00")),
        ]
        filters = NetWorthFilters(to_date=date(2026, 6, 30), currency="EUR")

        result = await service.net_worth_history(filters, group_by="month")

        totals = {i.period: i.total for i in result.items}
        assert totals["2026-01"] == Decimal("500.00")
        assert totals["2026-02"] == Decimal("550.00")

    async def test_accounts_without_opening_balance_are_ignored_as_anchors(self, service):
        account = MagicMock(id=1, opening_balance=None, opening_balance_date=None)
        service._account_repo.list.return_value = [account]
        service._repo.get_ledger_events.return_value = [
            (1, date(2026, 6, 1), Decimal("100.00")),
        ]
        filters = NetWorthFilters(to_date=date(2026, 6, 30), currency="EUR")

        result = await service.net_worth_history(filters, group_by="month")

        assert {i.period: i.total for i in result.items} == {"2026-06": Decimal("100.00")}

    async def test_from_date_injects_anchor_point_for_prior_history(self, service):
        service._account_repo.list.return_value = []
        service._repo.get_ledger_events.return_value = [
            (1, date(2026, 1, 1), Decimal("1000.00")),
            (1, date(2026, 6, 1), Decimal("-200.00")),
        ]
        filters = NetWorthFilters(
            from_date=date(2026, 5, 15), to_date=date(2026, 6, 30), currency="EUR"
        )

        result = await service.net_worth_history(filters, group_by="month")

        assert result.items[0].period == "2026-05"
        assert result.items[0].total == Decimal("1000.00")
        assert result.items[-1].total == Decimal("800.00")

    async def test_global_currency_passes_none_account_currency_filter(self, service):
        service._account_repo.list.return_value = []
        service._repo.get_ledger_events.return_value = []
        filters = NetWorthFilters(to_date=date(2026, 6, 30), currency="GLOBAL")

        await service.net_worth_history(filters, group_by="month")

        account_filters = service._account_repo.list.call_args.args[0]
        assert account_filters.currency is None


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
