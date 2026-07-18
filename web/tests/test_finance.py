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

        assert "?period=this+month&currency=BRL" in resp.text.replace("&amp;", "&")

    def test_no_toggle_for_single_currency(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls, [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/")

        assert "currency=BRL" not in resp.text


class TestFinanceDashboardPeriods:
    def _fake_get(self, calls, accounts, spending=None, by_category=None, all_txns=None):
        async def fake(path, params=None):
            params = params or {}
            calls.append((path, params))
            if path == "/finance/accounts":
                return accounts
            if path == "/finance/transactions/report" and spending is not None:
                return spending
            if path == "/finance/transactions/by-category" and by_category is not None:
                return by_category
            if path == "/finance/transactions" and params.get("limit") == 500 and all_txns is not None:
                return all_txns
            return []
        return fake

    def test_quarter_and_semester_chips_present(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [], [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/")

        assert "This quarter" in resp.text
        assert "This semester" in resp.text
        assert "period=this quarter" in resp.text
        assert "period=this semester" in resp.text

    def test_quarter_period_passed_to_api(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls, [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/?period=this quarter")

        assert resp.status_code == 200
        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["period"] == "this quarter"
        assert "from_date" not in report_call

    def test_custom_range_uses_from_and_to_instead_of_period(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(
            calls, [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/?from_date=2026-01-01&to_date=2026-03-15")

        assert resp.status_code == 200
        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call == {"from_date": "2026-01-01", "to_date": "2026-03-15", "currency": "EUR"}
        assert "period" not in report_call
        txn_call = next(p for path, p in calls if path == "/finance/transactions" and p.get("limit") == 15)
        assert txn_call["from_date"] == "2026-01-01"
        assert txn_call["to_date"] == "2026-03-15"

    def test_custom_range_button_shows_selected_dates(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [], [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/?from_date=2026-01-01&to_date=2026-03-15")

        assert "2026-01-01 → 2026-03-15" in resp.text
        assert 'value="2026-01-01"' in resp.text
        assert 'value="2026-03-15"' in resp.text

    def test_no_quick_period_highlighted_when_custom_active(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [], [{"id": 1, "name": "Checking", "currency": "EUR"}]
        )

        resp = client.get("/finance/?from_date=2026-01-01&to_date=2026-03-15")

        assert resp.status_code == 200
        # the this-month chip must not carry the active/highlighted classes
        assert 'bg-[#E6F1FB] text-[#0C447C]">This month</a>' not in resp.text

    def test_currency_toggle_preserves_custom_range(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [],
            [
                {"id": 1, "name": "Checking", "currency": "EUR"},
                {"id": 2, "name": "Conta BR", "currency": "BRL"},
            ],
        )

        resp = client.get("/finance/?from_date=2026-01-01&to_date=2026-03-15")

        text = resp.text.replace("&amp;", "&")
        assert "from_date=2026-01-01&to_date=2026-03-15&currency=BRL" in text

    def test_long_range_groups_spending_by_month(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [],
            [{"id": 1, "name": "Checking", "currency": "EUR"}],
            spending={"total": "10.00", "currency": "EUR", "from_date": "2026-01-01", "to_date": "2026-06-30", "transaction_count": 1},
            all_txns=[_txn(id=1, amount="10.00")],
        )

        resp = client.get("/finance/?period=this semester")

        assert "(month)" in resp.text.lower()

    def test_short_range_groups_spending_by_day(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(
            [],
            [{"id": 1, "name": "Checking", "currency": "EUR"}],
            spending={"total": "10.00", "currency": "EUR", "from_date": "2026-06-01", "to_date": "2026-06-30", "transaction_count": 1},
            all_txns=[_txn(id=1, amount="10.00")],
        )

        resp = client.get("/finance/?period=this month")

        assert "(day)" in resp.text.lower()

    def test_new_transaction_refresh_uses_custom_range(self, client, mock_api):
        calls = []

        async def fake_get(path, params=None):
            calls.append((path, params or {}))
            return []
        mock_api["get"].side_effect = fake_get
        mock_api["post"].return_value = {"id": 99}

        resp = client.post(
            "/finance/transactions?from_date=2026-01-01&to_date=2026-03-15",
            data={"amount": "10.00", "date": "2026-02-01", "type": "expense", "account_id": "1"},
        )

        assert resp.status_code == 200
        txn_call = next(p for path, p in calls if path == "/finance/transactions")
        assert txn_call["from_date"] == "2026-01-01"
        assert txn_call["to_date"] == "2026-03-15"
