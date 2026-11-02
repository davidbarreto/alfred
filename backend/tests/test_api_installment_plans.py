from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.finance.installment_plans.schemas import (
    InstallmentSlot,
    MissingInstallment,
    MissingInstallmentsMonth,
)

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_missing.return_value = [
        MissingInstallmentsMonth(
            month="2025-01",
            items=[
                MissingInstallment(
                    plan_id=1, description="SHOP", plan_ref="00001", position=3,
                    total_installments=9, status="missing",
                )
            ],
        )
    ]
    svc.get_slots.return_value = [InstallmentSlot(position=1, status="missing", expected_month="2025-01")]
    return svc


@pytest.fixture
def client(mock_service):
    from app.dependencies import get_installment_plan_service
    from app.main import app

    app.dependency_overrides[get_installment_plan_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListMissing:
    def test_returns_months_grouped(self, client, mock_service):
        response = client.get("/finance/installment-plans/missing?account_id=5", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body[0]["month"] == "2025-01"
        assert body[0]["items"][0]["position"] == 3
        mock_service.get_missing.assert_awaited_once_with(account_id=5)

    def test_static_route_not_shadowed_by_plan_id(self, client):
        assert client.get("/finance/installment-plans/missing", headers=AUTH).status_code == 200

    def test_requires_auth(self, client):
        assert client.get("/finance/installment-plans/missing").status_code in (401, 403)


class TestGetSlots:
    def test_returns_slots(self, client):
        response = client.get("/finance/installment-plans/1/slots", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["status"] == "missing"

    def test_unknown_plan_is_404(self, client, mock_service):
        mock_service.get_slots.return_value = None
        assert client.get("/finance/installment-plans/9/slots", headers=AUTH).status_code == 404
