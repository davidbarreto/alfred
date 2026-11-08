def _account(id=1, name="Checking"):
    return {"id": id, "name": name}


def _plan(**kwargs):
    plan = {
        "id": 1,
        "account_id": 1,
        "description": "Cetelem — sofa",
        "total_installments": 12,
        "captured_installments": 3,
        "plan_ref": None,
        "original_amount": None,
        "opened_date": "2026-06-01",
        "status": "open",
        "total_interest_paid": "1.50",
        "total_duty_paid": "0.20",
        "created_at": "2026-06-01T10:00:00",
    }
    plan.update(kwargs)
    return plan


def _transaction(**kwargs):
    txn = {
        "id": 10,
        "account_id": 1,
        "date": "2026-06-01T00:00:00",
        "amount": "50.00",
        "currency": "EUR",
        "type": "expense",
        "description": "Cetelem installment",
        "bank_description": "CETELEM PARC 3/12",
        "note": None,
        "installment_plan_id": 1,
        "amount_eur": "50.00",
        "created_at": "2026-06-01T10:00:00",
    }
    txn.update(kwargs)
    return txn


class TestInstallmentPlansPage:
    def test_renders_list_and_create_form(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_plan()],       # plans
            [],              # missing
            [_account()],    # accounts
        ]

        resp = client.get("/finance/installments")

        assert resp.status_code == 200
        assert "Installment plans" in resp.text
        assert "Cetelem — sofa" in resp.text
        assert "3/12" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/installments", follow_redirects=False)
        assert resp.status_code == 302

    def test_sorts_open_first_then_by_amount_desc(self, client, mock_api):
        closed_big = _plan(id=1, description="Closed big", status="closed", original_amount="900.00")
        open_small = _plan(id=2, description="Open small", status="open", original_amount="10.00")
        open_big = _plan(id=3, description="Open big", status="open", original_amount="500.00")
        mock_api["get"].side_effect = [
            [closed_big, open_small, open_big],
            [],
            [_account()],
        ]

        resp = client.get("/finance/installments")

        assert resp.status_code == 200
        pos_big = resp.text.index("Open big")
        pos_small = resp.text.index("Open small")
        pos_closed = resp.text.index("Closed big")
        assert pos_big < pos_small < pos_closed

    def test_hide_completed_filters_to_open_plans(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_plan()],
            [],
            [_account()],
        ]

        resp = client.get("/finance/installments?hide_completed=true")

        assert resp.status_code == 200
        mock_api["get"].assert_any_call("/finance/installment-plans", params={"status": "open"})
        assert "Show completed" in resp.text

    def test_account_filter_is_passed_to_api_and_preselected(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_plan()],
            [],
            [_account()],
        ]

        resp = client.get("/finance/installments?account_id=1&hide_completed=true")

        assert resp.status_code == 200
        mock_api["get"].assert_any_call(
            "/finance/installment-plans", params={"account_id": "1", "status": "open"}
        )
        assert 'name="account_id"' in resp.text
        assert 'value="1" selected' in resp.text
        assert 'name="hide_completed" value="true"' in resp.text


_MISSING = [
    {
        "month": "2025-01",
        "items": [
            {
                "plan_id": 1, "description": "Cetelem — sofa", "plan_ref": "00001",
                "position": 3, "total_installments": 12, "status": "missing",
            }
        ],
    }
]


class TestInstallmentPlansMissing:
    def test_shows_statements_to_import_and_plan_badge(self, client, mock_api):
        mock_api["get"].side_effect = [[_plan()], _MISSING, [_account()]]

        resp = client.get("/finance/installments")

        assert "Statements to import" in resp.text
        assert "2025-01" in resp.text
        assert "Cetelem — sofa 3/12" in resp.text
        assert "1 missing" in resp.text

    def test_hidden_when_nothing_is_missing(self, client, mock_api):
        mock_api["get"].side_effect = [[_plan()], [], [_account()]]

        resp = client.get("/finance/installments")

        assert "Statements to import" not in resp.text
        assert " missing" not in resp.text

    def test_account_filter_is_forwarded_to_missing_endpoint(self, client, mock_api):
        mock_api["get"].side_effect = [[_plan()], [], [_account()]]

        client.get("/finance/installments?account_id=1")

        mock_api["get"].assert_any_call("/finance/installment-plans/missing", params={"account_id": "1"})

    def test_page_still_renders_when_missing_endpoint_fails(self, client, mock_api):
        import httpx

        mock_api["get"].side_effect = [[_plan()], httpx.ConnectError("down"), [_account()]]

        resp = client.get("/finance/installments")

        assert resp.status_code == 200
        assert "Cetelem — sofa" in resp.text


class TestInstallmentCostTotals:
    def test_sums_interest_and_duty_of_listed_plans(self, client, mock_api):
        plans = [
            _plan(id=1, total_interest_paid="10.00", total_duty_paid="0.40"),
            _plan(id=2, description="Other", total_interest_paid="5.50", total_duty_paid="0.20"),
        ]
        mock_api["get"].side_effect = [plans, [], [_account()]]

        resp = client.get("/finance/installments")

        assert "Interest: €15.50" in resp.text
        assert "Duty: €0.60" in resp.text
        assert "Total cost: €16.10" in resp.text

    def test_no_totals_strip_without_plans(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [_account()]]

        resp = client.get("/finance/installments")

        assert "plan-cost-totals" not in resp.text


class TestRelinkInstallments:
    def test_posts_to_backend_and_redirects(self, client, mock_api):
        mock_api["post"].return_value = {"linked": 3}

        resp = client.post("/finance/installments/relink", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/finance/installments"
        mock_api["post"].assert_awaited_once_with("/finance/installment-plans/relink")


class TestCreateInstallmentPlan:
    def test_creates_and_redirects(self, client, mock_api):
        mock_api["post"].return_value = _plan()

        resp = client.post(
            "/finance/installments",
            data={
                "account_id": "1",
                "description": "Cetelem — sofa",
                "total_installments": "12",
                "opened_date": "2026-06-01",
                "pattern": "CETELEM",
                "mode": "auto",
            },
            follow_redirects=False,
        )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/finance/installments"
        mock_api["post"].assert_awaited_once()


class TestInstallmentPlanDetailPage:
    def test_renders_plan_and_transactions(self, client, mock_api):
        mock_api["get"].side_effect = [
            _plan(),                    # plan detail
            [_transaction()],           # linked transactions
            [],                         # slots
            [],                         # categories
            [],                         # tags
            [_account()],               # accounts
            [{"code": "EUR", "symbol": "€ "}],  # currencies
        ]

        resp = client.get("/finance/installments/1")

        assert resp.status_code == 200
        assert "Cetelem — sofa" in resp.text
        assert "Cetelem installment" in resp.text


class TestDeleteInstallmentPlan:
    def test_deletes_and_redirects(self, client, mock_api):
        resp = client.post("/finance/installments/1/delete", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/finance/installments"
        mock_api["delete"].assert_awaited_once_with("/finance/installment-plans/1")


class TestInstallmentPlanDetailSlots:
    def test_renders_slot_grid_with_missing_month(self, client, mock_api):
        slots = [
            {"position": 1, "status": "captured", "expected_month": "2024-12",
             "transaction_date": "2024-12-31", "amount": "-20.00", "transaction_id": 10},
            {"position": 2, "status": "missing", "expected_month": "2025-01"},
        ]
        mock_api["get"].side_effect = [
            _plan(), [_transaction()], slots, [], [], [_account()], [{"code": "EUR", "symbol": "€ "}],
        ]

        resp = client.get("/finance/installments/1")

        assert resp.status_code == 200
        assert "#2" in resp.text
        assert "missing · 2025-01" in resp.text
        assert "2024-12-31" in resp.text
