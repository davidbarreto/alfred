from freezegun import freeze_time
import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.budgets.service import BudgetTargetService
from app.features.finance.cycle import current_cycle_range
from app.features.finance.budgets.schemas import BudgetTargetRead, CategoryAverageSpend, CategoryBudgetStatus

FIXED_NOW = datetime(2026, 7, 15, 12, 0, 0)


def _make_category_orm(id, name):
    c = MagicMock()
    c.id = id
    c.name = name  # MagicMock(name=...) is reserved for the mock's repr, not an attribute
    return c


def _make_target_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.category_id = kwargs.get("category_id", 1)
    t.amount = kwargs.get("amount", Decimal("300.00"))
    t.effective_from = kwargs.get("effective_from", datetime(2026, 7, 1))
    t.effective_to = kwargs.get("effective_to", None)
    return t


@pytest.fixture
def service():
    svc = BudgetTargetService.__new__(BudgetTargetService)
    svc._session = AsyncMock()
    svc._repo = AsyncMock()
    svc._repo.add = MagicMock()  # add() is sync in the real repository
    svc._category_repo = AsyncMock()
    svc._txn_repo = AsyncMock()
    svc._settings = AsyncMock()
    svc._settings.get_cycle_start_day.return_value = 1
    return svc


class TestMonthRange:
    def test_regular_month(self):
        start, end = current_cycle_range(date(2026, 7, 10))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)

    def test_december_rollover(self):
        start, end = current_cycle_range(date(2026, 12, 5))
        assert start == date(2026, 12, 1)
        assert end == date(2026, 12, 31)


class TestListCurrentTargets:
    async def test_returns_budget_target_reads(self, service):
        service._repo.list_current.return_value = [_make_target_orm(id=i) for i in range(3)]
        result = await service.list_current_targets()
        assert len(result) == 3
        assert all(isinstance(t, BudgetTargetRead) for t in result)


CYCLE_START = datetime(2026, 7, 1)  # FIXED_NOW is 15 Jul with a cycle starting on the 1st


class TestSetTarget:
    async def test_first_ever_target_starts_at_cycle_start(self, service):
        service._repo.get_open.return_value = None
        service._repo.add.return_value = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=CYCLE_START)

        with freeze_time(FIXED_NOW):
            result = await service.set_target(1, Decimal("300"))

        service._repo.add.assert_called_once_with(category_id=1, amount=Decimal("300"), effective_from=CYCLE_START)
        assert isinstance(result, BudgetTargetRead)

    async def test_same_cycle_edit_updates_in_place(self, service):
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 7, 3, 9, 0))
        service._repo.get_open.return_value = open_target

        with freeze_time(FIXED_NOW):
            result = await service.set_target(1, Decimal("450"))

        assert open_target.amount == Decimal("450")
        assert open_target.effective_to is None
        service._repo.add.assert_not_called()
        assert isinstance(result, BudgetTargetRead)

    async def test_new_cycle_edit_closes_old_and_opens_new_at_cycle_boundary(self, service):
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 6, 10))
        service._repo.get_open.return_value = open_target
        service._repo.add.return_value = _make_target_orm(category_id=1, amount=Decimal("450"), effective_from=CYCLE_START)

        with freeze_time(FIXED_NOW):
            result = await service.set_target(1, Decimal("450"))

        assert open_target.effective_to == CYCLE_START
        service._repo.add.assert_called_once_with(category_id=1, amount=Decimal("450"), effective_from=CYCLE_START)
        assert isinstance(result, BudgetTargetRead)

    async def test_edit_on_cycle_start_day_offset_keeps_version_in_the_same_cycle(self, service):
        # Cycle starts on the 25th: on 4 Nov the active cycle began 25 Oct, so a
        # version created 28 Oct belongs to it and is overwritten, not versioned.
        service._settings.get_cycle_start_day.return_value = 25
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 10, 28))
        service._repo.get_open.return_value = open_target

        with freeze_time("2026-11-04 10:00:00"):
            await service.set_target(1, Decimal("450"))

        assert open_target.amount == Decimal("450")
        service._repo.add.assert_not_called()

    async def test_edit_in_new_offset_cycle_creates_version_starting_on_the_25th(self, service):
        service._settings.get_cycle_start_day.return_value = 25
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 10, 10))
        service._repo.get_open.return_value = open_target
        service._repo.add.return_value = _make_target_orm(category_id=1, amount=Decimal("450"))

        with freeze_time("2026-11-04 10:00:00"):
            await service.set_target(1, Decimal("450"))

        assert open_target.effective_to == datetime(2026, 10, 25)
        service._repo.add.assert_called_once_with(
            category_id=1, amount=Decimal("450"), effective_from=datetime(2026, 10, 25)
        )

    async def test_clear_closes_open_row_at_cycle_start_and_returns_none(self, service):
        open_target = _make_target_orm(category_id=1, effective_from=datetime(2026, 6, 1))
        service._repo.get_open.return_value = open_target

        with freeze_time(FIXED_NOW):
            result = await service.set_target(1, None)

        assert open_target.effective_to == CYCLE_START
        service._repo.add.assert_not_called()
        assert result is None

    async def test_clear_with_no_open_row_is_noop(self, service):
        service._repo.get_open.return_value = None
        result = await service.set_target(1, None)
        service._session.commit.assert_not_called()
        assert result is None


class TestSetTargetsBulk:
    async def test_sets_each_item_and_skips_cleared(self, service):
        service._repo.get_open.return_value = None
        service._repo.add.side_effect = [
            _make_target_orm(category_id=1, amount=Decimal("100")),
            _make_target_orm(category_id=2, amount=Decimal("200")),
        ]
        from app.features.finance.budgets.schemas import BudgetTargetBulkSetItem

        items = [
            BudgetTargetBulkSetItem(category_id=1, amount=Decimal("100")),
            BudgetTargetBulkSetItem(category_id=2, amount=Decimal("200")),
            BudgetTargetBulkSetItem(category_id=3, amount=None),
        ]
        results = await service.set_targets_bulk(items)
        assert len(results) == 2


class TestGetStatus:
    async def test_builds_status_per_effective_target(self, service):
        target = _make_target_orm(category_id=1, amount=Decimal("300.00"))
        service._repo.list_effective.return_value = [target]
        service._category_repo.list.return_value = [_make_category_orm(1, "Groceries")]
        service._txn_repo.get_spending_by_category.return_value = [(1, "Groceries", Decimal("120.00"), 4)]

        results = await service.get_status("2026-07")

        assert len(results) == 1
        assert isinstance(results[0], CategoryBudgetStatus)
        assert results[0].category_id == 1
        assert results[0].category_name == "Groceries"
        assert results[0].limit_amount == Decimal("300.00")
        assert results[0].spent == Decimal("120.00")
        assert results[0].year_month == date(2026, 7, 1)

    async def test_spent_is_zero_without_spending_and_uses_one_query(self, service):
        service._repo.list_effective.return_value = [
            _make_target_orm(category_id=1, amount=Decimal("300.00")),
            _make_target_orm(category_id=2, amount=Decimal("50.00")),
        ]
        service._category_repo.list.return_value = [_make_category_orm(1, "Groceries"), _make_category_orm(2, "Fun")]
        service._txn_repo.get_spending_by_category.return_value = [(1, "Groceries", Decimal("120.00"), 4)]

        results = await service.get_status("2026-07")

        assert [r.spent for r in results] == [Decimal("120.00"), Decimal("0")]
        service._txn_repo.get_spending_by_category.assert_awaited_once()

    async def test_passes_exclusive_next_month_boundary(self, service):
        service._repo.list_effective.return_value = []
        service._category_repo.list.return_value = []

        await service.get_status("2026-07")

        assert service._repo.list_effective.call_args[0] == (datetime(2026, 7, 1), datetime(2026, 8, 1))

    async def test_empty_targets_returns_empty_list(self, service):
        service._repo.list_effective.return_value = []
        service._category_repo.list.return_value = []
        results = await service.get_status("2026-07")
        assert results == []

    async def test_invalid_year_month_raises_value_error(self, service):
        with pytest.raises(ValueError):
            await service.get_status("not-a-month")

    async def test_none_year_month_uses_todays_active_cycle(self, service):
        service._repo.list_effective.return_value = []
        service._category_repo.list.return_value = []
        service._settings.get_cycle_start_day.return_value = 25

        with patch("app.features.finance.cycle.local_today", return_value=date(2026, 8, 15)):
            await service.get_status(None)

        # Aug 15 with cycle_start_day=25 -> active cycle started July 25 -> ends Aug 24
        assert service._repo.list_effective.call_args[0] == (datetime(2026, 7, 25), datetime(2026, 8, 25))


class TestGetAverageSpend:
    async def test_averages_total_over_completed_cycles_with_one_query(self, service):
        # Today is Jul 15: the completed cycles are Apr, May, Jun (Jul is in progress).
        service._txn_repo.get_spending_by_category.return_value = [
            (1, "Groceries", Decimal("450.00"), 8),
            (2, "Fun", Decimal("90.00"), 2),
        ]

        with patch("app.features.finance.budgets.service.local_today", return_value=date(2026, 7, 15)):
            results = await service.get_average_spend(3)

        by_id = {r.category_id: r for r in results}
        assert all(isinstance(r, CategoryAverageSpend) for r in results)
        assert by_id[1].average == Decimal("150.00")
        assert by_id[2].average == Decimal("30.00")
        assert by_id[1].category_name == "Groceries"
        assert by_id[1].months == 3
        service._txn_repo.get_spending_by_category.assert_awaited_once_with(date(2026, 4, 1), date(2026, 6, 30))

    async def test_uncategorized_spend_is_ignored(self, service):
        service._txn_repo.get_spending_by_category.return_value = [(None, None, Decimal("80.00"), 1)]

        results = await service.get_average_spend(1)

        assert results == []

    async def test_respects_cycle_start_day(self, service):
        service._settings.get_cycle_start_day.return_value = 25
        service._txn_repo.get_spending_by_category.return_value = []

        with patch("app.features.finance.budgets.service.local_today", return_value=date(2026, 8, 15)):
            await service.get_average_spend(2)

        # Aug 15 sits in the Jul 25 - Aug 24 cycle; the last two completed are May 25 - Jul 24.
        service._txn_repo.get_spending_by_category.assert_awaited_once_with(date(2026, 5, 25), date(2026, 7, 24))


class TestGetPeriod:
    async def test_defaults_to_todays_cycle_with_range(self, service):
        service._settings.get_cycle_start_day.return_value = 25

        with patch("app.features.finance.cycle.local_today", return_value=date(2026, 11, 4)):
            period = await service.get_period(None)

        assert period.year_month == "2026-10"
        assert period.from_date == date(2026, 10, 25)
        assert period.to_date == date(2026, 11, 24)

    async def test_requested_label_returns_its_range(self, service):
        service._settings.get_cycle_start_day.return_value = 25

        period = await service.get_period("2026-12")

        assert (period.year_month, period.from_date, period.to_date) == ("2026-12", date(2026, 12, 25), date(2027, 1, 24))

    async def test_invalid_label_raises_value_error(self, service):
        with pytest.raises(ValueError):
            await service.get_period("nope")


class TestGetHistory:
    async def test_returns_current_and_previous_cycles_newest_first(self, service):
        service._settings.get_cycle_start_day.return_value = 25
        service._category_repo.list.return_value = [_make_category_orm(1, "Groceries")]
        service._repo.list_effective.side_effect = [
            [_make_target_orm(category_id=1, amount=Decimal("300"))],
            [_make_target_orm(category_id=1, amount=Decimal("250"))],
            [],
        ]
        service._txn_repo.get_spending_by_category.return_value = [(1, "Groceries", Decimal("100"), 2)]

        with patch("app.features.finance.budgets.service.local_today", return_value=date(2026, 11, 4)):
            history = await service.get_history(3)

        assert [h.year_month for h in history] == ["2026-10", "2026-09", "2026-08"]
        assert (history[0].from_date, history[0].to_date) == (date(2026, 10, 25), date(2026, 11, 24))
        assert (history[1].from_date, history[1].to_date) == (date(2026, 9, 25), date(2026, 10, 24))
        assert [h.items[0].limit_amount if h.items else None for h in history] == [Decimal("300"), Decimal("250"), None]
        assert history[0].items[0].spent == Decimal("100")
        service._category_repo.list.assert_awaited_once()
