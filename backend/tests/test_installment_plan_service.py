from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

from app.features.finance.installment_plans.schemas import InstallmentPlanCreate
from app.features.finance.installment_plans.service import InstallmentPlanService


def _plan(**kwargs):
    from unittest.mock import MagicMock

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
    p.created_at = kwargs.get("created_at", datetime(2026, 7, 1, 12, 0, 0))
    return p


def _service() -> InstallmentPlanService:
    service = InstallmentPlanService(session=AsyncMock())
    service._repo = AsyncMock()
    service._import_repo = AsyncMock()
    service._txn_repo = AsyncMock()
    return service


class TestCreatePlanWithRule:
    async def test_creates_plan_and_matching_rule(self):
        service = _service()
        plan = _plan()
        service._repo.create.return_value = plan

        result = await service.create_plan_with_rule(
            InstallmentPlanCreate(
                account_id=1,
                description="COMPRA IKEA",
                total_installments=3,
                opened_date=date(2026, 7, 1),
                pattern="IKEA",
                amount=None,
                mode="auto",
            )
        )

        service._repo.create.assert_awaited_once_with(
            account_id=1, description="COMPRA IKEA", total_installments=3, opened_date=date(2026, 7, 1),
            plan_ref=None, original_amount=None,
        )
        service._import_repo.create_rule.assert_awaited_once()
        rule_data = service._import_repo.create_rule.call_args[0][0]
        assert rule_data.pattern == "IKEA"
        assert rule_data.installment_plan_id == plan.id
        assert result.id == plan.id
        assert result.captured_installments == 0


class TestEnsurePlanForRef:
    async def test_returns_existing_plan_without_creating(self):
        service = _service()
        existing = _plan(id=7, plan_ref="00024")
        service._repo.get_by_account_and_plan_ref.return_value = existing
        service._repo.get_with_captured_count.return_value = (existing, 2)

        plan, created = await service.ensure_plan_for_ref(
            account_id=1, plan_ref="00024", description="COMPRA IKEA",
            total_installments=3, original_amount=Decimal("428.83"), opened_date=date(2026, 7, 1),
        )

        assert created is False
        assert plan.id == 7
        service._repo.create.assert_not_awaited()

    async def test_creates_new_plan_when_not_found(self):
        service = _service()
        service._repo.get_by_account_and_plan_ref.return_value = None
        created_plan = _plan(id=9, plan_ref="00024")
        service._repo.create.return_value = created_plan

        plan, created = await service.ensure_plan_for_ref(
            account_id=1, plan_ref="00024", description="COMPRA IKEA",
            total_installments=3, original_amount=Decimal("428.83"), opened_date=date(2026, 7, 1),
        )

        assert created is True
        assert plan.id == 9
        service._repo.create.assert_awaited_once_with(
            account_id=1, description="COMPRA IKEA", total_installments=3,
            opened_date=date(2026, 7, 1), plan_ref="00024", original_amount=Decimal("428.83"),
        )
        rule_data = service._import_repo.create_rule.call_args[0][0]
        assert rule_data.pattern == "00024"


class TestGet:
    async def test_returns_read_model_with_captured_count(self):
        service = _service()
        plan = _plan()
        service._repo.get_with_captured_count.return_value = (plan, 2)

        result = await service.get(1)

        assert result.captured_installments == 2
        assert result.id == plan.id

    async def test_none_when_not_found(self):
        service = _service()
        service._repo.get_with_captured_count.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_maps_all_plans(self):
        service = _service()
        plans = [_plan(id=1), _plan(id=2)]
        service._repo.list.return_value = [(plans[0], 1), (plans[1], 0)]

        result = await service.list(account_id=1, status="open")

        service._repo.list.assert_awaited_once_with(1, "open")
        assert [r.captured_installments for r in result] == [1, 0]


class TestUpdate:
    async def test_returns_updated_plan(self):
        service = _service()
        plan = _plan(description="New")
        service._repo.update.return_value = plan
        service._repo.get_with_captured_count.return_value = (plan, 1)

        result = await service.update(1, "New", None)

        assert result.description == "New"

    async def test_none_when_not_found(self):
        service = _service()
        service._repo.update.return_value = None

        assert await service.update(999, "x", None) is None


class TestDelete:
    async def test_deletes_plan_and_its_rules(self):
        service = _service()
        service._import_repo.delete_rules_by_installment_plan.return_value = 1
        service._repo.delete.return_value = True

        assert await service.delete(1) is True
        service._import_repo.delete_rules_by_installment_plan.assert_awaited_once_with(1)
        service._txn_repo.delete_placeholder_for_plan.assert_awaited_once_with(1)
        service._repo.delete.assert_awaited_once_with(1)

    async def test_returns_false_when_plan_not_found(self):
        service = _service()
        service._import_repo.delete_rules_by_installment_plan.return_value = 0
        service._repo.delete.return_value = False

        assert await service.delete(999) is False
