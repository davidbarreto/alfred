from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.shopping.schemas import PurchaseFrequencyFilters, PurchaseFrequencyRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _row(**kwargs):
    defaults = dict(
        product_id=1, name="Milk", category_id=1, purchase_count=3,
        first_bought_on=date(2026, 10, 1), last_bought_on=date(2026, 10, 13),
        avg_interval_days=6.0, days_since_last=7, next_expected_on=date(2026, 10, 19),
    )
    defaults.update(kwargs)
    return PurchaseFrequencyRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.list_purchase_frequency.return_value = [_row()]
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_shopping_service
    app.dependency_overrides[get_shopping_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListPurchaseFrequency:
    def test_returns_rows(self, client):
        response = client.get("/organizer/shopping/insights/frequency", headers=AUTH)

        assert response.status_code == 200
        row = response.json()[0]
        assert (row["name"], row["avg_interval_days"], row["next_expected_on"]) == ("Milk", 6.0, "2026-10-19")

    def test_defaults_to_two_purchases_minimum(self, client, mock_service):
        client.get("/organizer/shopping/insights/frequency", headers=AUTH)

        assert mock_service.list_purchase_frequency.call_args[0][0] == PurchaseFrequencyFilters()

    def test_filters_are_passed_through(self, client, mock_service):
        client.get(
            "/organizer/shopping/insights/frequency", params={"min_purchases": 1, "category_id": 3, "limit": 10}, headers=AUTH
        )

        assert mock_service.list_purchase_frequency.call_args[0][0] == PurchaseFrequencyFilters(
            min_purchases=1, category_id=3, limit=10
        )

    def test_is_not_shadowed_by_the_item_id_route(self, client):
        assert client.get("/organizer/shopping/insights/frequency", headers=AUTH).status_code != 422

    def test_requires_auth(self, client):
        assert client.get("/organizer/shopping/insights/frequency").status_code == 403
