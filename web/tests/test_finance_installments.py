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
            [_account()],
        ]

        resp = client.get("/finance/installments?hide_completed=true")

        assert resp.status_code == 200
        mock_api["get"].assert_any_call("/finance/installment-plans", params={"status": "open"})
        assert "Show completed" in resp.text


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
            [],                         # categories
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
