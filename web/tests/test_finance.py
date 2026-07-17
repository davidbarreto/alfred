def _txn(id=1, merchant="Continente", amount="30.00", type="expense", category_id=None, account_id=1):
    return {
        "id": id, "account_id": account_id, "date": "2026-07-14T22:35:14",
        "amount": amount, "currency": "EUR", "type": type,
        "category_id": category_id, "description": None, "merchant": merchant,
        "source": None, "created_at": "2026-07-14T22:35:14",
    }


def _category(id=1, name="Groceries"):
    return {"id": id, "name": name}


def _account(id=1, name="Checking"):
    return {"id": id, "name": name}


class TestTransactionsPage:
    def test_renders_transactions(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_txn(id=1, merchant="Continente")],
            [_category()],
            [_account()],
        ]

        resp = client.get("/finance/transactions")

        assert resp.status_code == 200
        assert "Continente" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/transactions", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")

    def test_type_filter_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], []]

        client.get("/finance/transactions?type=income")

        calls = mock_api["get"].call_args_list
        txn_call = next(c for c in calls if c.args[0] == "/finance/transactions")
        assert txn_call.kwargs["params"]["type"] == "income"

    def test_merchant_filter_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], []]

        client.get("/finance/transactions?merchant=Continente")

        calls = mock_api["get"].call_args_list
        txn_call = next(c for c in calls if c.args[0] == "/finance/transactions")
        assert txn_call.kwargs["params"]["merchant"] == "Continente"

    def test_offset_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], []]

        client.get("/finance/transactions?offset=20")

        calls = mock_api["get"].call_args_list
        txn_call = next(c for c in calls if c.args[0] == "/finance/transactions")
        assert txn_call.kwargs["params"]["offset"] == 20


class TestTransactionsListFragment:
    def test_shows_next_when_more_than_page_size(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_txn(id=i) for i in range(21)],
            [],
            [],
        ]

        resp = client.get("/finance/transactions/list")

        assert resp.status_code == 200
        assert "changeTxnPage(1)" in resp.text

    def test_no_pagination_footer_for_short_list(self, client, mock_api):
        mock_api["get"].side_effect = [[_txn(id=1)], [], []]

        resp = client.get("/finance/transactions/list")

        assert resp.status_code == 200
        assert "changeTxnPage(1)" not in resp.text

    def test_empty_state_message(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], []]

        resp = client.get("/finance/transactions/list")

        assert "No transactions match these filters" in resp.text


class TestDeleteTransaction:
    def test_delete_with_offset_renders_list_partial(self, client, mock_api):
        mock_api["get"].side_effect = [[_txn(id=2)], [], []]

        resp = client.delete("/finance/transactions/1?offset=0")

        assert resp.status_code == 200
        mock_api["delete"].assert_any_await("/finance/transactions/1")
        # the paginated list partial targets #txn-list-full; the dashboard one targets #transaction-list
        assert 'hx-target="#txn-list-full"' in resp.text

    def test_delete_without_offset_renders_dashboard_partial(self, client, mock_api):
        mock_api["get"].return_value = [_txn(id=2)]

        resp = client.delete("/finance/transactions/1")

        assert resp.status_code == 200
        mock_api["delete"].assert_any_await("/finance/transactions/1")

    def test_requires_authentication(self, anon_client):
        resp = anon_client.delete("/finance/transactions/1", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestFinanceDashboardCurrency:
    def _fake_get(self, calls, accounts):
        async def fake(path, params=None):
            calls.append((path, params or {}))
            if path == "/finance/accounts":
                return accounts
            return []
        return fake

    def test_defaults_to_eur_and_fetches_budgets(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls, [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/")

        assert resp.status_code == 200
        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["currency"] == "EUR"
        assert any(path == "/finance/budgets/remaining" for path, _ in calls)

    def test_brl_view_filters_and_skips_budgets(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls,
            [
                {"id": 1, "name": "Checking", "currency": "EUR"},
                {"id": 2, "name": "Conta BR", "currency": "BRL"},
            ],
        )

        resp = client.get("/finance/?currency=BRL")

        assert resp.status_code == 200
        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["currency"] == "BRL"
        txn_call = next(p for path, p in calls if path == "/finance/transactions")
        assert txn_call["currency"] == "BRL"
        assert not any(path == "/finance/budgets/remaining" for path, _ in calls)
        assert 'R$' in resp.text or "R$" in resp.text

    def test_currency_toggle_shown_only_with_multiple_currencies(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls,
            [
                {"id": 1, "name": "Checking", "currency": "EUR"},
                {"id": 2, "name": "Conta BR", "currency": "BRL"},
            ],
        )

        resp = client.get("/finance/")

        assert "?period=this month&currency=BRL" in resp.text.replace("&amp;", "&")

    def test_no_toggle_for_single_currency(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls, [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/")

        assert "currency=BRL" not in resp.text
