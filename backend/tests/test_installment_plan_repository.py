from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.installment_plans.repository import InstallmentPlanRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    return r


def _row_first(row):
    r = MagicMock()
    r.first.return_value = row
    return r


def _rows_all(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


def _scalar(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _plan(**kwargs):
    p = MagicMock()
    p.id = kwargs.get("id", 1)
    p.account_id = kwargs.get("account_id", 1)
    p.description = kwargs.get("description", "COMPRA IKEA")
    p.total_installments = kwargs.get("total_installments", 3)
    p.plan_ref = kwargs.get("plan_ref", None)
    p.original_amount = kwargs.get("original_amount", Decimal("428.83"))
    p.opened_date = kwargs.get("opened_date", date(2026, 7, 1))
    p.status = kwargs.get("status", "open")
    p.total_interest_paid = kwargs.get("total_interest_paid", Decimal("0"))
    p.total_duty_paid = kwargs.get("total_duty_paid", Decimal("0"))
    return p


class TestGet:
    async def test_found(self):
        session = _make_session()
        plan = _plan()
        session.execute.return_value = _scalar_first(plan)
        assert await InstallmentPlanRepository(session).get(1) == plan

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await InstallmentPlanRepository(session).get(999) is None


class TestGetWithCapturedCount:
    async def test_returns_plan_and_count(self):
        session = _make_session()
        plan = _plan()
        session.execute.return_value = _row_first((plan, 2))
        result = await InstallmentPlanRepository(session).get_with_captured_count(1)
        assert result == (plan, 2)

    async def test_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _row_first(None)
        assert await InstallmentPlanRepository(session).get_with_captured_count(999) is None


class TestGetOpenByAccountAndDescription:
    async def test_found(self):
        session = _make_session()
        plan = _plan()
        session.execute.return_value = _scalar_first(plan)
        result = await InstallmentPlanRepository(session).get_open_by_account_and_description(1, "x")
        assert result == plan

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await InstallmentPlanRepository(session).get_open_by_account_and_description(1, "x")
        assert result is None


class TestGetByAccountAndPlanRef:
    async def test_found(self):
        session = _make_session()
        plan = _plan(plan_ref="00024")
        session.execute.return_value = _scalar_first(plan)
        result = await InstallmentPlanRepository(session).get_by_account_and_plan_ref(1, "00024")
        assert result == plan

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await InstallmentPlanRepository(session).get_by_account_and_plan_ref(1, "00024")
        assert result is None


class TestList:
    async def test_returns_plans_with_counts(self):
        session = _make_session()
        plans = [_plan(id=1), _plan(id=2)]
        session.execute.return_value = _rows_all([(plans[0], 1), (plans[1], 3)])
        result = await InstallmentPlanRepository(session).list()
        assert result == [(plans[0], 1), (plans[1], 3)]


class TestCreate:
    async def test_creates_open_plan(self):
        session = _make_session()
        repo = InstallmentPlanRepository(session)
        plan = await repo.create(
            account_id=1, description="COMPRA IKEA", total_installments=3, opened_date=date(2026, 7, 1)
        )
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.status == "open"
        assert added.total_installments == 3
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert plan is added

    async def test_creates_with_plan_ref_and_original_amount(self):
        session = _make_session()
        repo = InstallmentPlanRepository(session)
        await repo.create(
            account_id=1, description="COMPRA IKEA", total_installments=3,
            opened_date=date(2026, 7, 1), plan_ref="00024", original_amount=Decimal("428.83"),
        )
        added = session.add.call_args[0][0]
        assert added.plan_ref == "00024"
        assert added.original_amount == Decimal("428.83")


class TestUpdate:
    async def test_updates_fields(self):
        session = _make_session()
        plan = _plan()
        session.execute.return_value = _scalar_first(plan)
        result = await InstallmentPlanRepository(session).update(1, "New desc", 5)
        assert result.description == "New desc"
        assert result.total_installments == 5

    async def test_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await InstallmentPlanRepository(session).update(999, "x", None)
        assert result is None


class TestDelete:
    async def test_deletes_and_returns_true(self):
        session = _make_session()
        plan = _plan()
        session.execute.return_value = _scalar_first(plan)
        assert await InstallmentPlanRepository(session).delete(1) is True
        session.delete.assert_awaited_once_with(plan)

    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await InstallmentPlanRepository(session).delete(999) is False


class TestRecordCapture:
    async def test_accumulates_interest_and_duty(self):
        session = _make_session()
        plan = _plan(total_installments=3)
        session.execute.side_effect = [_scalar_first(plan), _scalar(1)]

        result = await InstallmentPlanRepository(session).record_capture(
            1, juros=Decimal("0.81"), imposto_selo=Decimal("0.03")
        )

        assert result.total_interest_paid == Decimal("0.81")
        assert result.total_duty_paid == Decimal("0.03")

    async def test_closes_plan_once_captured_reaches_total(self):
        session = _make_session()
        plan = _plan(total_installments=2, status="open")
        session.execute.side_effect = [_scalar_first(plan), _scalar(2)]

        result = await InstallmentPlanRepository(session).record_capture(1, juros=None, imposto_selo=None)

        assert result.status == "closed"

    async def test_stays_open_when_captured_below_total(self):
        session = _make_session()
        plan = _plan(total_installments=3, status="open")
        session.execute.side_effect = [_scalar_first(plan), _scalar(1)]

        result = await InstallmentPlanRepository(session).record_capture(1, juros=None, imposto_selo=None)

        assert result.status == "open"

    async def test_none_when_plan_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await InstallmentPlanRepository(session).record_capture(999, juros=None, imposto_selo=None)
        assert result is None


class TestRecomputeStatus:
    async def test_reopens_closed_plan_once_below_total(self):
        # record_capture only ever moves a plan towards closed (captures only
        # increase there); unlinking a transaction is the one path that can drop
        # a closed plan back under its total_installments.
        session = _make_session()
        plan = _plan(total_installments=3, status="closed")
        session.execute.side_effect = [_scalar_first(plan), _scalar(2)]

        result = await InstallmentPlanRepository(session).recompute_status(1)

        assert result.status == "open"

    async def test_stays_closed_when_still_at_or_above_total(self):
        session = _make_session()
        plan = _plan(total_installments=2, status="closed")
        session.execute.side_effect = [_scalar_first(plan), _scalar(2)]

        result = await InstallmentPlanRepository(session).recompute_status(1)

        assert result.status == "closed"

    async def test_none_when_plan_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await InstallmentPlanRepository(session).recompute_status(999)
        assert result is None
