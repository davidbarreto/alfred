import httpx


def _account(id=1, name="Checking"):
    return {"id": id, "name": name}


def _category(id=10, name="Groceries"):
    return {"id": id, "name": name}


def _batch(id=7):
    return {
        "id": id, "account_id": 1, "provider": "activobank",
        "source_file": "mov.csv", "stored_file": "activobank/abc_mov.csv",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30", "closing_balance": "2539.65",
        "inserted_count": 10, "duplicate_count": 2,
        "created_at": "2026-07-17T10:00:00",
    }


def _preview_row(**kwargs):
    row = {
        "date_posted": "2026-06-01",
        "date_value": "2026-06-01",
        "bank_description": "COMPRA 8597 PINGO DOCE CONTACTLESS",
        "amount": "-23.17",
        "balance_after": "471.09",
        "type": "expense",
        "status": "new",
        "deduplication_hash": "abc123",
        "description": "Pingo Doce",
        "merchant": "Pingo Doce",
        "category_id": 10,
        "category_name": "Groceries",
        "counterpart_account_id": None,
        "suggestion_source": "rule_auto",
        "confidence": None,
        "needs_review": False,
    }
    row.update(kwargs)
    return row


def _preview(rows=None):
    rows = rows if rows is not None else [_preview_row()]
    return {
        "provider": "activobank",
        "account_id": 1,
        "source_file": "mov.csv",
        "stored_file": "activobank/abc_mov.csv",
        "currency": "EUR",
        "account_number": "456",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "closing_balance": "2539.65",
        "rows": rows,
        "new_count": sum(1 for r in rows if r["status"] == "new"),
        "duplicate_count": sum(1 for r in rows if r["status"] == "duplicate"),
        "needs_review_count": sum(1 for r in rows if r["needs_review"]),
    }


def _rule(id=1, **kwargs):
    rule = {
        "id": id, "pattern": "PINGO DOCE", "amount": None, "mode": "auto",
        "description": "Pingo Doce", "merchant": "Pingo Doce",
        "category_id": 10, "transfer_account_id": None,
        "created_at": "2026-07-17T10:00:00",
    }
    rule.update(kwargs)
    return rule


class TestImportPage:
    def test_renders_upload_form_batches_and_rules(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_account()],          # accounts (active)
            ["activobank"],        # providers
            [_batch()],            # batches
            [_account()],          # accounts for batches context
            [_rule()],             # rules
            [_category()],         # categories for rules context
            [_account()],          # accounts for rules context
        ]

        resp = client.get("/finance/import")

        assert resp.status_code == 200
        assert "Import bank statement" in resp.text
        assert "activobank" in resp.text
        assert "Checking" in resp.text
        assert "Categorization rules" in resp.text
        assert "PINGO DOCE" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/import", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestImportPreview:
    def test_renders_review_table(self, client, mock_api):
        mock_api["post_multipart"].return_value = _preview()
        mock_api["get"].side_effect = [[_account()], [_category()]]

        resp = client.post(
            "/finance/import/preview",
            data={"account_id": "1", "provider": "activobank"},
            files={"file": ("mov.csv", b"csv-bytes", "text/csv")},
        )

        assert resp.status_code == 200
        assert "PINGO DOCE" in resp.text
        assert "Review import" in resp.text
        assert "1 new" in resp.text
        call = mock_api["post_multipart"].call_args
        assert call.args[0] == "/finance/imports/preview"
        assert call.kwargs["data"]["account_id"] == "1"
        assert call.kwargs["data"]["provider"] == "activobank"

    def test_duplicate_rows_marked_skipped(self, client, mock_api):
        rows = [_preview_row(), _preview_row(status="duplicate", deduplication_hash="dup1")]
        mock_api["post_multipart"].return_value = _preview(rows)
        mock_api["get"].side_effect = [[_account()], [_category()]]

        resp = client.post(
            "/finance/import/preview",
            data={"account_id": "1"},
            files={"file": ("mov.csv", b"x", "text/csv")},
        )

        assert "already imported" in resp.text

    def test_parse_failure_returns_error(self, client, mock_api):
        mock_api["post_multipart"].side_effect = httpx.HTTPError("boom")

        resp = client.post(
            "/finance/import/preview",
            data={"account_id": "1"},
            files={"file": ("weird.txt", b"???", "text/plain")},
        )

        assert resp.status_code == 422
        assert "Could not parse" in resp.text


class TestImportCommit:
    def test_builds_payload_from_form(self, client, mock_api):
        mock_api["post"].return_value = {
            "batch_id": 7, "inserted": 1, "skipped_duplicates": 0, "rules_created": 1
        }

        resp = client.post(
            "/finance/import/commit",
            data={
                "account_id": "1",
                "provider": "activobank",
                "source_file": "mov.csv",
                "currency": "EUR",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "closing_balance": "2539.65",
                "stored_file": "activobank/abc_mov.csv",
                "row_count": "2",
                # row 0: included, categorized, saves a rule
                "include_0": "on",
                "date_0": "2026-06-01",
                "bank_description_0": "COMPRA 8597 PINGO DOCE",
                "amount_0": "-23.17",
                "type_0": "expense",
                "hash_0": "abc123",
                "description_0": "Pingo Doce",
                "merchant_0": "Pingo Doce",
                "note_0": "",
                "category_0": "10",
                "save_rule_0": "on",
                "rule_pattern_0": "PINGO DOCE",
                "rule_mode_0": "auto",
                # row 1: not included (no include_1 key)
                "date_1": "2026-06-02",
                "bank_description_1": "OTHER",
                "amount_1": "-5.00",
                "type_1": "expense",
                "hash_1": "def456",
            },
        )

        assert resp.status_code == 200
        assert "Imported" in resp.text
        payload = mock_api["post"].call_args.kwargs["json"]
        assert payload["account_id"] == 1
        assert payload["stored_file"] == "activobank/abc_mov.csv"
        assert len(payload["rows"]) == 1
        row = payload["rows"][0]
        assert row["deduplication_hash"] == "abc123"
        assert row["category_id"] == 10
        assert row["save_rule"] is True
        assert row["rule_pattern"] == "PINGO DOCE"
        assert "note" not in row

    def test_commit_failure_returns_error(self, client, mock_api):
        mock_api["post"].side_effect = httpx.HTTPError("boom")

        resp = client.post(
            "/finance/import/commit",
            data={"account_id": "1", "provider": "activobank", "row_count": "0"},
        )

        assert resp.status_code == 422


class TestImportBatches:
    def test_delete_batch_refreshes_list(self, client, mock_api):
        mock_api["get"].side_effect = [[], [_account()]]

        resp = client.request("DELETE", "/finance/import/batches/7")

        assert resp.status_code == 200
        assert "No imports yet" in resp.text
        mock_api["delete"].assert_awaited_once_with("/finance/imports/7")

    def test_batches_fragment(self, client, mock_api):
        mock_api["get"].side_effect = [[_batch()], [_account()]]

        resp = client.get("/finance/import/batches")

        assert resp.status_code == 200
        assert "activobank" in resp.text
        assert "/finance/import/batches/7/file" in resp.text

    def test_download_original_file(self, client, mock_api):
        mock_api["get_bytes"].return_value = (b"csv-bytes", "text/csv")

        resp = client.get("/finance/import/batches/7/file")

        assert resp.status_code == 200
        assert resp.content == b"csv-bytes"
        mock_api["get_bytes"].assert_awaited_once_with("/finance/imports/7/file")

    def test_download_missing_file_404(self, client, mock_api):
        mock_api["get_bytes"].side_effect = httpx.HTTPError("not found")

        resp = client.get("/finance/import/batches/7/file")

        assert resp.status_code == 404


class TestImportRules:
    def test_rules_fragment(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_rule(), _rule(id=2, pattern="PoupeUp", category_id=None, description=None,
                            merchant=None, transfer_account_id=1)],
            [_category()],
            [_account()],
        ]

        resp = client.get("/finance/import/rules")

        assert resp.status_code == 200
        assert "PINGO DOCE" in resp.text
        assert "Groceries" in resp.text
        assert "Transfer → Checking" in resp.text

    def test_create_rule_builds_payload(self, client, mock_api):
        mock_api["get"].side_effect = [[_rule()], [_category()], [_account()]]

        resp = client.post(
            "/finance/import/rules",
            data={
                "pattern": " PoupeUp ",
                "mode": "auto",
                "amount": "-10,00",
                "description": "",
                "merchant": "",
                "category_id": "",
                "transfer_account_id": "1",
            },
        )

        assert resp.status_code == 200
        payload = mock_api["post"].call_args.kwargs["json"]
        assert payload["pattern"] == "PoupeUp"
        assert payload["amount"] == "-10.00"
        assert payload["transfer_account_id"] == 1
        assert "category_id" not in payload

    def test_create_rule_failure_returns_422(self, client, mock_api):
        mock_api["post"].side_effect = httpx.HTTPError("boom")

        resp = client.post("/finance/import/rules", data={"pattern": "X", "mode": "auto"})

        assert resp.status_code == 422

    def test_delete_rule_refreshes_list(self, client, mock_api):
        mock_api["get"].side_effect = [[], [_category()], [_account()]]

        resp = client.request("DELETE", "/finance/import/rules/1")

        assert resp.status_code == 200
        assert "No rules yet" in resp.text
        mock_api["delete"].assert_awaited_once_with("/finance/imports/rules/1")
