import httpx


def _txn(id=1, merchant="Continente", amount="30.00", type="expense", category_id=None, account_id=1, currency="EUR"):
    return {
        "id": id, "account_id": account_id, "date": "2026-07-14T22:35:14",
        "amount": amount, "currency": currency, "type": type,
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
            [],
        ]

        resp = client.get("/finance/transactions")

        assert resp.status_code == 200
        assert "Continente" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/transactions", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")

    def test_type_filter_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [], []]

        client.get("/finance/transactions?type=income")

        calls = mock_api["get"].call_args_list
        txn_call = next(c for c in calls if c.args[0] == "/finance/transactions")
        assert txn_call.kwargs["params"]["type"] == "income"

    def test_merchant_filter_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [], []]

        client.get("/finance/transactions?merchant=Continente")

        calls = mock_api["get"].call_args_list
        txn_call = next(c for c in calls if c.args[0] == "/finance/transactions")
        assert txn_call.kwargs["params"]["merchant"] == "Continente"

    def test_offset_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [], []]

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
            [],
        ]

        resp = client.get("/finance/transactions/list")

        assert resp.status_code == 200
        assert "changeTxnPage(1)" in resp.text

    def test_no_pagination_footer_for_short_list(self, client, mock_api):
        mock_api["get"].side_effect = [[_txn(id=1)], [], [], []]

        resp = client.get("/finance/transactions/list")

        assert resp.status_code == 200
        assert "changeTxnPage(1)" not in resp.text

    def test_empty_state_message(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [], []]

        resp = client.get("/finance/transactions/list")

        assert "No transactions match these filters" in resp.text

    def test_uses_symbol_for_non_major_currency(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/finance/transactions":
                return [_txn(id=1, currency="PLN")]
            if path == "/finance/currencies":
                return [{"code": "PLN", "symbol": "zł", "name": "Polish Zloty"}]
            return []
        mock_api["get"].side_effect = fake_get

        resp = client.get("/finance/transactions/list")

        assert "zł" in resp.text


class TestDeleteTransaction:
    def test_delete_with_offset_renders_list_partial(self, client, mock_api):
        mock_api["get"].side_effect = [[_txn(id=2)], [], [], []]

        resp = client.delete("/finance/transactions/1?offset=0")

        assert resp.status_code == 200
        mock_api["delete"].assert_any_await("/finance/transactions/1")
        # the paginated list partial targets #txn-list-full; the dashboard one targets #transaction-list
        assert 'hx-target="#txn-list-full"' in resp.text

    def test_delete_without_offset_renders_dashboard_partial(self, client, mock_api):
        async def fake_get(path, params=None):
            if path == "/finance/transactions":
                return [_txn(id=2)]
            return []
        mock_api["get"].side_effect = fake_get

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
            if path == "/finance/currencies":
                return [
                    {"code": "EUR", "symbol": "€", "name": "Euro"},
                    {"code": "BRL", "symbol": "R$", "name": "Brazilian Real"},
                    {"code": "USD", "symbol": "$", "name": "US Dollar"},
                    {"code": "GBP", "symbol": "£", "name": "British Pound"},
                ]
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
        assert any(path == "/finance/budgets/status" for path, _ in calls)

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
        assert not any(path == "/finance/budgets/status" for path, _ in calls)
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

    def test_renders_transaction_list_with_account_and_category_names(self, client, mock_api):
        async def fake(path, params=None):
            if path == "/finance/accounts":
                return [{"id": 1, "name": "Checking", "currency": "EUR"}]
            if path == "/finance/categories":
                return [_category(id=1, name="Groceries")]
            if path == "/finance/transactions":
                return [_txn(id=1, account_id=1, category_id=1)]
            return []

        mock_api["get"].side_effect = fake

        resp = client.get("/finance/")

        assert resp.status_code == 200
        assert "Checking" in resp.text
        assert "Groceries" in resp.text


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


class TestUpdateTransaction:
    def _fake_get(self, calls, extra=None):
        extra = extra or {}
        async def fake(path, params=None):
            calls.append((path, params or {}))
            return extra.get(path, [])
        return fake

    def test_offset_present_renders_list_partial(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(calls)
        mock_api["patch"].return_value = {"id": 1}

        resp = client.patch(
            "/finance/transactions/1?offset=20",
            data={"amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1"},
        )

        assert resp.status_code == 200
        mock_api["patch"].assert_awaited_once()
        assert mock_api["patch"].call_args.args[0] == "/finance/transactions/1"
        # list-page context fetches paginated transactions, not the dashboard's range-scoped ones
        assert any(p.get("offset") == 20 for path, p in calls if path == "/finance/transactions")

    def test_no_offset_renders_dashboard_partial(self, client, mock_api):
        calls = []
        mock_api["get"].side_effect = self._fake_get(calls)
        mock_api["patch"].return_value = {"id": 1}

        resp = client.patch(
            "/finance/transactions/1?period=this quarter&currency=BRL",
            data={"amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1"},
        )

        assert resp.status_code == 200
        txn_call = next(p for path, p in calls if path == "/finance/transactions")
        assert txn_call["period"] == "this quarter"
        assert txn_call["currency"] == "BRL"

    def test_payload_always_includes_clearable_fields(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get([])
        mock_api["patch"].return_value = {"id": 1}

        client.patch(
            "/finance/transactions/1?period=this month",
            data={
                "amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1",
                "merchant": "", "description": "", "note": "", "category_id": "",
            },
        )

        payload = mock_api["patch"].call_args.kwargs["json"]
        assert payload["merchant"] is None
        assert payload["description"] is None
        assert payload["note"] is None
        assert payload["category_id"] is None

    def test_category_and_note_forwarded_when_set(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get([])
        mock_api["patch"].return_value = {"id": 1}

        client.patch(
            "/finance/transactions/1?period=this month",
            data={
                "amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1",
                "category_id": "5", "note": "Kenai's lunch",
            },
        )

        payload = mock_api["patch"].call_args.kwargs["json"]
        assert payload["category_id"] == 5
        assert payload["note"] == "Kenai's lunch"

    def test_backend_failure_returns_error(self, client, mock_api):
        mock_api["patch"].side_effect = httpx.HTTPError("boom")

        resp = client.patch(
            "/finance/transactions/1?period=this month",
            data={"amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1"},
        )

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.patch(
            "/finance/transactions/1",
            data={"amount": "10.00", "date": "2026-06-01", "type": "expense", "account_id": "1"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestFinanceSessionPersistence:
    def _fake_get(self):
        async def fake(path, params=None):
            return []
        return fake

    def test_explicit_period_is_remembered_on_next_bare_visit(self, client, mock_api):
        calls = []
        async def fake(path, params=None):
            calls.append((path, params or {}))
            return []
        mock_api["get"].side_effect = fake

        client.get("/finance/?period=this quarter")
        calls.clear()
        client.get("/finance/")

        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["period"] == "this quarter"

    def test_custom_range_is_remembered_on_next_bare_visit(self, client, mock_api):
        calls = []
        async def fake(path, params=None):
            calls.append((path, params or {}))
            return []
        mock_api["get"].side_effect = fake

        client.get("/finance/?from_date=2026-01-01&to_date=2026-03-15")
        calls.clear()
        client.get("/finance/")

        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call == {"from_date": "2026-01-01", "to_date": "2026-03-15", "currency": "EUR"}

    def test_explicit_query_param_overrides_remembered_range(self, client, mock_api):
        calls = []
        async def fake(path, params=None):
            calls.append((path, params or {}))
            return []
        mock_api["get"].side_effect = fake

        client.get("/finance/?period=this quarter")
        calls.clear()
        client.get("/finance/?period=this year")

        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["period"] == "this year"

    def test_currency_is_remembered_on_next_bare_visit(self, client, mock_api):
        calls = []
        async def fake(path, params=None):
            calls.append((path, params or {}))
            if path == "/finance/accounts":
                return [{"id": 1, "name": "Conta BR", "currency": "BRL"}]
            return []
        mock_api["get"].side_effect = fake

        client.get("/finance/?currency=BRL")
        calls.clear()
        client.get("/finance/")

        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["currency"] == "BRL"

    def test_fresh_session_defaults_to_this_month_and_eur(self, client, mock_api):
        calls = []
        async def fake(path, params=None):
            calls.append((path, params or {}))
            return []
        mock_api["get"].side_effect = fake

        client.get("/finance/")

        report_call = next(p for path, p in calls if path == "/finance/transactions/report")
        assert report_call["period"] == "this month"
        assert report_call["currency"] == "EUR"


class TestDeleteAccount:
    def _http_status_error(self, detail: str) -> httpx.HTTPStatusError:
        request = httpx.Request("DELETE", "http://backend/finance/accounts/1")
        response = httpx.Response(409, json={"detail": detail}, request=request)
        return httpx.HTTPStatusError("Conflict", request=request, response=response)

    def test_surfaces_transaction_count_from_api(self, client, mock_api):
        mock_api["delete"].side_effect = self._http_status_error(
            "Cannot delete this account: it still has 187 transaction(s). "
            "Deactivate the account instead, or delete its transactions first."
        )
        mock_api["get"].return_value = []

        resp = client.delete("/finance/accounts/1")

        assert resp.status_code == 422
        assert "187 transaction(s)" in resp.text

    def test_generic_error_when_response_not_json(self, client, mock_api):
        request = httpx.Request("DELETE", "http://backend/finance/accounts/1")
        response = httpx.Response(409, content=b"not json", request=request)
        mock_api["delete"].side_effect = httpx.HTTPStatusError(
            "Conflict", request=request, response=response
        )

        resp = client.delete("/finance/accounts/1")

        assert resp.status_code == 422
        assert "Failed to delete account" in resp.text

    def test_successful_delete_refreshes_list(self, client, mock_api):
        mock_api["delete"].return_value = None
        mock_api["get"].return_value = []

        resp = client.delete("/finance/accounts/1")

        assert resp.status_code == 200
        mock_api["delete"].assert_awaited_once_with("/finance/accounts/1")


class TestBulkMoveTransactions:
    def _http_status_error(self, detail: str) -> httpx.HTTPStatusError:
        request = httpx.Request("POST", "http://backend/finance/transactions/bulk-move")
        response = httpx.Response(400, json={"detail": detail}, request=request)
        return httpx.HTTPStatusError("Bad Request", request=request, response=response)

    def test_forwards_required_fields(self, client, mock_api):
        mock_api["post"].return_value = {"moved_count": 5}

        resp = client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": "1", "target_account_id": "2"},
        )

        assert resp.status_code == 200
        payload = mock_api["post"].call_args.kwargs["json"]
        assert payload == {"account_id": 1, "target_account_id": 2}

    def test_forwards_optional_filters_when_present(self, client, mock_api):
        mock_api["post"].return_value = {"moved_count": 5}

        client.post(
            "/finance/transactions/bulk-move",
            json={
                "account_id": "1", "target_account_id": "2",
                "type": "expense", "category_id": "3", "merchant": "Uber",
                "from_date": "2026-06-01", "to_date": "2026-06-30",
            },
        )

        payload = mock_api["post"].call_args.kwargs["json"]
        assert payload["type"] == "expense"
        assert payload["category_id"] == 3
        assert payload["merchant"] == "Uber"
        assert payload["from_date"] == "2026-06-01"
        assert payload["to_date"] == "2026-06-30"

    def test_omits_empty_optional_filters(self, client, mock_api):
        mock_api["post"].return_value = {"moved_count": 5}

        client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": "1", "target_account_id": "2", "type": "", "merchant": ""},
        )

        payload = mock_api["post"].call_args.kwargs["json"]
        assert "type" not in payload
        assert "merchant" not in payload

    def test_surfaces_api_error_detail(self, client, mock_api):
        mock_api["post"].side_effect = self._http_status_error("Target account not found")

        resp = client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": "1", "target_account_id": "999"},
        )

        assert resp.status_code == 422
        assert "Target account not found" in resp.text

    def test_generic_error_when_response_not_json(self, client, mock_api):
        request = httpx.Request("POST", "http://backend/finance/transactions/bulk-move")
        response = httpx.Response(400, content=b"not json", request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "Bad Request", request=request, response=response
        )

        resp = client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": "1", "target_account_id": "2"},
        )

        assert resp.status_code == 422
        assert "Failed to move transactions" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post(
            "/finance/transactions/bulk-move",
            json={"account_id": "1", "target_account_id": "2"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestTransactionsPageBulkMoveButton:
    def test_shown_when_account_filter_set(self, client, mock_api):
        mock_api["get"].side_effect = [[], [_account()], [], []]

        resp = client.get("/finance/transactions?account_id=1")

        assert "Move to account" in resp.text

    def test_hidden_without_account_filter(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], [], []]

        resp = client.get("/finance/transactions")

        assert "Move to account" not in resp.text


def _budget_target(category_id=1, amount="300.00"):
    return {
        "id": category_id, "category_id": category_id, "amount": amount,
        "effective_from": "2026-07-01T00:00:00", "effective_to": None,
    }


def _budget_status(category_id=1, category_name="Groceries", limit_amount="300.00", spent="120.00"):
    return {
        "category_id": category_id, "category_name": category_name,
        "year_month": "2026-07-01", "limit_amount": limit_amount, "spent": spent,
    }


class TestBudgetsPage:
    def _fake_get(self, targets=None, status=None):
        targets = targets if targets is not None else [_budget_target()]
        status = status if status is not None else [_budget_status()]

        async def fake(path, params=None):
            if path == "/finance/categories":
                return [_category(id=1, name="Groceries")]
            if path == "/finance/budgets/targets":
                return targets
            if path == "/finance/currencies":
                return [{"code": "EUR", "symbol": "€", "name": "Euro"}]
            if path == "/finance/budgets/status":
                return status
            return []
        return fake

    def test_renders_targets_and_chart(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get()

        resp = client.get("/finance/budgets")

        assert resp.status_code == 200
        assert "Groceries" in resp.text
        assert 'value="300.00"' in resp.text

    def test_empty_state_when_no_target_set(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get(targets=[], status=[])

        resp = client.get("/finance/budgets")

        assert resp.status_code == 200
        assert "No tracked categories for this month" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/budgets", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestSetBudgetTargets:
    def _fake_get(self):
        async def fake(path, params=None):
            if path == "/finance/categories":
                return [_category(id=1, name="Groceries")]
            if path == "/finance/budgets/targets":
                return [_budget_target(amount="350.00")]
            if path == "/finance/currencies":
                return [{"code": "EUR", "symbol": "€", "name": "Euro"}]
            return []
        return fake

    def test_saves_and_returns_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = self._fake_get()
        mock_api["put"].return_value = [_budget_target(amount="350.00")]

        resp = client.put(
            "/finance/budgets/targets",
            json={"targets": [{"category_id": 1, "amount": "350.00"}]},
        )

        assert resp.status_code == 200
        mock_api["put"].assert_awaited_once_with(
            "/finance/budgets/targets", json={"targets": [{"category_id": 1, "amount": "350.00"}]}
        )
        assert 'value="350.00"' in resp.text

    def test_invalid_payload_returns_422(self, client, mock_api):
        resp = client.put("/finance/budgets/targets", json={"nope": []})
        assert resp.status_code == 422

    def test_upstream_failure_returns_422(self, client, mock_api):
        mock_api["put"].side_effect = httpx.HTTPError("boom")

        resp = client.put("/finance/budgets/targets", json={"targets": []})

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.put("/finance/budgets/targets", json={"targets": []}, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestBudgetStatusJson:
    def test_returns_status_list(self, client, mock_api):
        mock_api["get"].return_value = [_budget_status()]

        resp = client.get("/finance/budgets/status.json?year_month=2026-07")

        assert resp.status_code == 200
        assert resp.json()[0]["category_name"] == "Groceries"
        mock_api["get"].assert_awaited_once_with("/finance/budgets/status", params={"year_month": "2026-07"})

    def test_defaults_to_no_params(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/finance/budgets/status.json")

        assert resp.status_code == 200
        mock_api["get"].assert_awaited_once_with("/finance/budgets/status", params={})

    def test_upstream_failure_returns_empty_list(self, client, mock_api):
        mock_api["get"].side_effect = httpx.HTTPError("boom")

        resp = client.get("/finance/budgets/status.json")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/finance/budgets/status.json", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")
