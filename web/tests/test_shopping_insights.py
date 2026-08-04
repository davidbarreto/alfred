def _frequent_item(name="Beans", category_id=1, purchase_count=5, last_bought_at="2026-07-01T00:00:00"):
    return {"name": name, "category_id": category_id, "purchase_count": purchase_count, "last_bought_at": last_bought_at}


def _category(id=1, name="Grocery"):
    return {"id": id, "name": name}


def _fake_get(frequent=None, by_category=None, by_month=None, priority_split=None, by_store=None, categories=None):
    frequent = frequent or []
    by_category = by_category or []
    by_month = by_month or []
    priority_split = priority_split or []
    by_store = by_store or []
    categories = categories or []

    async def fake_get(path, params=None):
        if path == "/organizer/shopping/frequent":
            return frequent
        if path == "/organizer/shopping/insights/by-category":
            return by_category
        if path == "/organizer/shopping/insights/by-month":
            return by_month
        if path == "/organizer/shopping/insights/priority-split":
            return priority_split
        if path == "/organizer/shopping/insights/by-store":
            return by_store
        if path == "/organizer/shopping-categories":
            return categories
        return []

    return fake_get


class TestFrequentProducts:
    def test_renders_top_items_from_frequent_endpoint(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(
            frequent=[_frequent_item(name="Beans", purchase_count=8), _frequent_item(name="Milk", purchase_count=3)],
        )

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert "Beans" in resp.text
        assert "Milk" in resp.text

    def test_no_data_message_when_empty(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get()

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert "No data" in resp.text


class TestByCategoryChart:
    def test_resolves_category_ids_to_names(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(
            by_category=[{"category_id": 1, "purchase_count": 4}],
            categories=[_category(id=1, name="Grocery")],
        )

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert "Grocery" in resp.text

    def test_falls_back_to_id_when_category_unresolved(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(
            by_category=[{"category_id": 99, "purchase_count": 4}],
            categories=[],
        )

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert "#99" in resp.text


class TestByMonthChart:
    def test_renders_months_in_chronological_order(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(
            by_month=[
                {"month": "2026-05", "purchase_count": 3},
                {"month": "2026-06", "purchase_count": 7},
            ],
        )

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        may_pos = resp.text.index('"2026-05"')
        jun_pos = resp.text.index('"2026-06"')
        assert may_pos < jun_pos

    def test_requests_six_month_window_by_default(self, client, mock_api):
        seen_params = []

        async def fake_get(path, params=None):
            if path == "/organizer/shopping/insights/by-month":
                seen_params.append(params)
            return []

        mock_api["get"].side_effect = fake_get

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert seen_params[0]["months"] == 6


class TestPrioritySplit:
    def test_renders_need_and_want_counts(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(
            priority_split=[{"priority": "need", "item_count": 5}, {"priority": "want", "item_count": 2}],
        )

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert "Need vs want" in resp.text
        assert "No data" not in resp.text.split("Need vs want")[1][:200]


class TestByStoreConditional:
    def test_omitted_when_empty(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(by_store=[])

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert 'id="chart-by-store"' not in resp.text

    def test_rendered_when_populated(self, client, mock_api):
        mock_api["get"].side_effect = _fake_get(by_store=[{"store": "Aldi", "purchase_count": 4}])

        resp = client.get("/shopping/insights/")

        assert resp.status_code == 200
        assert 'id="chart-by-store"' in resp.text
