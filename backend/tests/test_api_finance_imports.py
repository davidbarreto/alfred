import pytest
from datetime import date, datetime
from decimal import Decimal
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from app.features.finance.imports.schemas import (
    ImportBatchRead,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportPreviewRow,
    ImportRuleRead,
)

AUTH = {"Authorization": "Bearer test-api-token"}


def _preview_row(**kwargs):
    defaults = dict(
        date_posted=date(2026, 6, 1),
        date_value=date(2026, 6, 1),
        bank_description="COMPRA 8597 PINGO DOCE CONTACTLESS",
        amount=Decimal("-23.17"),
        balance_after=Decimal("471.09"),
        type="expense",
        status="new",
        deduplication_hash="abc123",
        category_id=10,
        category_name="Groceries",
        suggestion_source="rule_auto",
    )
    defaults.update(kwargs)
    return ImportPreviewRow(**defaults)


def _preview_response():
    return ImportPreviewResponse(
        provider="activobank",
        account_id=1,
        source_file="mov.csv",
        currency="EUR",
        account_number="456",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        closing_balance=Decimal("2539.65"),
        rows=[_preview_row()],
        new_count=1,
        duplicate_count=0,
        needs_review_count=0,
    )


def _batch_read(**kwargs):
    defaults = dict(
        id=7,
        account_id=1,
        provider="activobank",
        source_file="mov.csv",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        closing_balance=Decimal("2539.65"),
        inserted_count=10,
        duplicate_count=2,
        created_at=datetime(2026, 7, 17, 10, 0),
    )
    defaults.update(kwargs)
    return ImportBatchRead(**defaults)


def _rule_read(**kwargs):
    defaults = dict(
        id=1,
        pattern="PINGO DOCE",
        amount=None,
        mode="auto",
        description="Pingo Doce",
        merchant="Pingo Doce",
        category_id=10,
        transfer_account_id=None,
        created_at=datetime(2026, 7, 17, 10, 0),
    )
    defaults.update(kwargs)
    return ImportRuleRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.available_providers = MagicMock(return_value=["activobank"])
    svc.preview.return_value = _preview_response()
    svc.commit.return_value = ImportCommitResponse(
        batch_id=7, inserted=10, skipped_duplicates=2, rules_created=1
    )
    svc.list_batches.return_value = [_batch_read()]
    svc.delete_batch.return_value = True
    svc.list_rules.return_value = [_rule_read()]
    svc.create_rule.return_value = _rule_read(id=2)
    svc.delete_rule.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_import_service
    app.dependency_overrides[get_import_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestProviders:
    def test_lists_providers(self, client):
        response = client.get("/finance/imports/providers", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == ["activobank"]

    def test_requires_auth(self, client):
        assert client.get("/finance/imports/providers").status_code == 403


class TestPreview:
    def test_preview_upload(self, client, mock_service):
        response = client.post(
            "/finance/imports/preview",
            headers=AUTH,
            data={"account_id": "1", "provider": "activobank"},
            files={"file": ("mov.csv", b"csv-bytes", "text/csv")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "activobank"
        assert body["rows"][0]["category_name"] == "Groceries"
        kwargs = mock_service.preview.call_args.kwargs
        assert kwargs["account_id"] == 1
        assert kwargs["filename"] == "mov.csv"
        assert kwargs["provider"] == "activobank"

    def test_preview_without_provider_autodetects(self, client, mock_service):
        response = client.post(
            "/finance/imports/preview",
            headers=AUTH,
            data={"account_id": "1"},
            files={"file": ("mov.csv", b"csv-bytes", "text/csv")},
        )
        assert response.status_code == 200
        assert mock_service.preview.call_args.kwargs["provider"] is None

    def test_unparseable_file_returns_422(self, client, mock_service):
        mock_service.preview.return_value = None
        response = client.post(
            "/finance/imports/preview",
            headers=AUTH,
            data={"account_id": "1"},
            files={"file": ("weird.txt", b"???", "text/plain")},
        )
        assert response.status_code == 422


class TestCommit:
    def test_commit(self, client, mock_service):
        payload = {
            "account_id": 1,
            "provider": "activobank",
            "source_file": "mov.csv",
            "currency": "EUR",
            "rows": [
                {
                    "date_posted": "2026-06-01",
                    "bank_description": "COMPRA 8597 PINGO DOCE",
                    "amount": "-23.17",
                    "type": "expense",
                    "deduplication_hash": "abc123",
                    "description": "Pingo Doce",
                    "category_id": 10,
                    "save_rule": True,
                    "rule_pattern": "PINGO DOCE",
                }
            ],
        }
        response = client.post("/finance/imports/commit", headers=AUTH, json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["batch_id"] == 7
        assert body["inserted"] == 10
        request = mock_service.commit.call_args[0][0]
        assert request.rows[0].save_rule is True

    def test_requires_auth(self, client):
        assert client.post("/finance/imports/commit", json={}).status_code == 403


class TestBatches:
    def test_list_batches(self, client):
        response = client.get("/finance/imports", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["id"] == 7

    def test_delete_batch(self, client):
        assert client.delete("/finance/imports/7", headers=AUTH).status_code == 204

    def test_delete_missing_batch_404(self, client, mock_service):
        mock_service.delete_batch.return_value = False
        assert client.delete("/finance/imports/99", headers=AUTH).status_code == 404

    def test_download_batch_file(self, client, mock_service):
        mock_service.get_batch_file.return_value = (b"csv-bytes", "mov.csv")
        response = client.get("/finance/imports/7/file", headers=AUTH)
        assert response.status_code == 200
        assert response.content == b"csv-bytes"
        assert 'filename="mov.csv"' in response.headers["content-disposition"]

    def test_download_missing_file_404(self, client, mock_service):
        mock_service.get_batch_file.return_value = None
        assert client.get("/finance/imports/7/file", headers=AUTH).status_code == 404


class TestRules:
    def test_list_rules(self, client):
        response = client.get("/finance/imports/rules", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["pattern"] == "PINGO DOCE"

    def test_create_rule(self, client):
        payload = {"pattern": "PAYSHOP", "amount": "-10.00", "mode": "suggest"}
        response = client.post("/finance/imports/rules", headers=AUTH, json=payload)
        assert response.status_code == 201
        assert response.json()["id"] == 2

    def test_delete_rule(self, client):
        assert client.delete("/finance/imports/rules/1", headers=AUTH).status_code == 204

    def test_delete_missing_rule_404(self, client, mock_service):
        mock_service.delete_rule.return_value = False
        assert client.delete("/finance/imports/rules/9", headers=AUTH).status_code == 404
