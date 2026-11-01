import httpx
import pytest


def _item(id=1, name="Milk", category_id=1, status="pending"):
    return {"id": id, "name": name, "category_id": category_id, "status": status,
             "priority": "need", "quantity": None, "unit": None, "brand": None,
             "estimated_price": None, "source": "manual"}


def _category(id=1, name="grocery"):
    return {"id": id, "name": name}


def _route_get(routes: dict):
    """Build an AsyncMock side_effect that returns a canned value per API path prefix."""
    async def _side_effect(path, params=None):
        for prefix, value in routes.items():
            if path.startswith(prefix):
                return value
        return []
    return _side_effect


@pytest.fixture(autouse=True)
def categories(mock_api):
    """Every shopping route fetches /organizer/shopping-categories; default it to a
    single 'grocery' category unless a test overrides mock_api['get'].side_effect."""
    mock_api["get"].side_effect = _route_get({"/organizer/shopping-categories": [_category()]})
    return [_category()]


class TestAddShoppingItem:
    def test_creates_item_and_renders_updated_list(self, client, mock_api):
        mock_api["post"].return_value = _item()
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping/frequent": [],
            "/organizer/shopping": [_item()],
        })

        resp = client.post("/shopping/", data={"name": "Milk", "category_id": "1", "priority": "need"})

        assert resp.status_code == 200
        assert "Milk" in resp.text
        mock_api["post"].assert_any_await("/organizer/shopping", json={
            "name": "Milk", "category_id": 1, "priority": "need", "source": "manual",
        })
        mock_api["get"].assert_any_await(
            "/organizer/shopping", params={"status": "pending", "limit": 100}
        )
        mock_api["get"].assert_any_await(
            "/organizer/shopping/frequent", params={"limit": 5}
        )

    def test_creates_item_with_optional_fields(self, client, mock_api):
        mock_api["post"].return_value = _item()
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping/frequent": [],
            "/organizer/shopping": [_item()],
        })

        resp = client.post("/shopping/", data={
            "name": "Milk", "category_id": "1", "priority": "need",
            "quantity": "2", "unit": "L", "estimated_price": "3.50",
            "brand": "Nesquik", "store": "Lidl", "url": "https://example.com/milk",
            "notes": "Lactose-free",
        })

        assert resp.status_code == 200
        mock_api["post"].assert_any_await("/organizer/shopping", json={
            "name": "Milk", "category_id": 1, "priority": "need", "source": "manual",
            "quantity": "2", "unit": "L", "estimated_price": "3.50",
            "brand": "Nesquik", "store": "Lidl", "url": "https://example.com/milk",
            "notes": "Lactose-free",
        })

    def test_returns_422_when_backend_create_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/shopping")
        mock_api["post"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.post("/shopping/", data={"name": "Milk", "category_id": "1"})

        assert resp.status_code == 422


def _conflict(path: str, detail: str, method: str = "POST") -> httpx.HTTPStatusError:
    request = httpx.Request(method, f"http://api{path}")
    return httpx.HTTPStatusError(
        "409", request=request, response=httpx.Response(409, json={"detail": detail}, request=request)
    )


class TestAddRejectedAsDuplicate:
    def test_shows_the_backend_message_and_keeps_the_list(self, client, mock_api):
        mock_api["post"].side_effect = _conflict("/organizer/shopping", "'Milk' is already on the shopping list (item 3)")
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping/frequent": [],
            "/organizer/shopping": [_item(id=3)],
        })

        resp = client.post("/shopping/", data={"name": "Milk", "category_id": "1"})

        assert resp.status_code == 200
        assert "already on the shopping list (item 3)" in resp.text
        assert 'id="shopping-add-error"' in resp.text
        assert "Milk" in resp.text

    def test_success_clears_any_previous_error(self, client, mock_api):
        mock_api["post"].return_value = _item()

        resp = client.post("/shopping/", data={"name": "Milk", "category_id": "1"})

        assert 'id="shopping-add-error"' in resp.text
        assert "already on the shopping list" not in resp.text


class TestShoppingNameSuggestions:
    def test_returns_suggestions_from_backend(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping/names": [{"name": "Bananas", "category_id": 1}],
        })

        resp = client.get("/shopping/names?name=ban")

        assert resp.status_code == 200
        assert "Bananas" in resp.text
        mock_api["get"].assert_any_await(
            "/organizer/shopping/names", params={"q": "ban", "limit": 8}
        )

    def test_returns_empty_fragment_when_query_blank(self, client, mock_api):
        resp = client.get("/shopping/names?name=")

        assert resp.status_code == 200
        assert resp.text.strip() == ""
        for call in mock_api["get"].await_args_list:
            assert call.args[0] != "/organizer/shopping/names"

    def test_renders_empty_fragment_on_backend_error(self, client, mock_api):
        request = httpx.Request("GET", "http://api/organizer/shopping/names")

        async def _side_effect(path, params=None):
            if path == "/organizer/shopping/names":
                raise httpx.ConnectError("connection refused", request=request)
            return []

        mock_api["get"].side_effect = _side_effect

        resp = client.get("/shopping/names?name=ban")

        assert resp.status_code == 200
        assert resp.text.strip() == ""


class TestAcceptRecurringItem:
    def test_accepts_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping/frequent": [],
            "/organizer/recurrence/due": [],
            "/organizer/shopping": [_item(name="Bananas")],
        })

        resp = client.post("/shopping/recurring/5/accept")

        assert resp.status_code == 200
        assert "Bananas" in resp.text
        mock_api["post"].assert_awaited_once_with("/organizer/recurrence/5/accept")

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/recurrence/5/accept")
        mock_api["post"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.post("/shopping/recurring/5/accept")

        assert resp.status_code == 422


class TestShoppingPage:
    def test_renders_api_error_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/organizer/shopping")

        async def _side_effect(path, params=None):
            if path == "/organizer/shopping":
                raise httpx.ConnectError("connection refused", request=request)
            return []

        mock_api["get"].side_effect = _side_effect

        resp = client.get("/shopping/")

        assert resp.status_code == 200
        assert "Cannot reach backend" in resp.text


class TestAddWishlistItem:
    def test_creates_item_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category(id=2, name="electronics")],
            "/organizer/wishlist": [{"id": 1, "name": "Headphones", "category_id": 2,
                                      "brand": None, "estimated_price": None}],
        })

        resp = client.post("/shopping/wishlist", data={"name": "Headphones", "category_id": "2"})

        assert resp.status_code == 200
        assert "Headphones" in resp.text
        mock_api["post"].assert_awaited_once_with(
            "/organizer/wishlist", json={"name": "Headphones", "category_id": 2}
        )


class TestShoppingCategories:
    def test_create_category_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category(), _category(id=2, name="frozen")],
        })

        resp = client.post("/shopping/categories", data={"name": "frozen"})

        assert resp.status_code == 200
        assert "frozen" in resp.text
        mock_api["post"].assert_awaited_once_with(
            "/organizer/shopping-categories", json={"name": "frozen"}
        )

    def test_delete_category_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({"/organizer/shopping-categories": [_category()]})

        resp = client.delete("/shopping/categories/5")

        assert resp.status_code == 200
        mock_api["delete"].assert_awaited_once_with("/organizer/shopping-categories/5")

    def test_returns_422_when_delete_blocked(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/organizer/shopping-categories/5")
        mock_api["delete"].side_effect = httpx.HTTPStatusError(
            "409", request=request, response=httpx.Response(409, request=request)
        )

        resp = client.delete("/shopping/categories/5")

        assert resp.status_code == 422


def _product(id=1, name="Milk", category_id=1, default_unit="l", purchase_count=3, pending=False, default_quantity=None):
    return {"id": id, "name": name, "category_id": category_id, "default_unit": default_unit,
            "default_quantity": default_quantity, "purchase_count": purchase_count, "pending": pending}


class TestShoppingProducts:
    def test_page_lists_products_on_their_tab(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product(name="Olive oil", default_unit="l")],
        })

        resp = client.get("/shopping/")

        assert resp.status_code == 200
        assert 'id="panel-products"' in resp.text
        assert 'value="Olive oil"' in resp.text
        assert "3 bought" in resp.text

    def test_search_passes_the_query_to_the_backend(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product()],
        })

        resp = client.get("/shopping/products", params={"q": "mil"})

        assert resp.status_code == 200
        mock_api["get"].assert_any_await("/organizer/shopping-products", params={"limit": 500, "q": "mil"})

    def test_update_sends_name_category_unit_and_quantity(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product(name="Whole milk")],
        })

        resp = client.post("/shopping/products/4", data={
            "name": "Whole milk", "category_id": "1", "default_unit": "l", "default_quantity": "2",
        })

        assert resp.status_code == 200
        mock_api["patch"].assert_awaited_once_with("/organizer/shopping-products/4", json={
            "name": "Whole milk", "category_id": 1, "default_unit": "l", "default_quantity": "2",
        })
        assert "Whole milk" in resp.text

    def test_update_clears_blank_unit(self, client, mock_api):
        client.post("/shopping/products/4", data={"name": "Milk", "category_id": "1", "default_unit": ""})

        payload = mock_api["patch"].await_args.kwargs["json"]
        assert payload["default_unit"] is None
        assert payload["default_quantity"] is None

    def test_rename_clash_shows_the_message_and_reloads_the_list(self, client, mock_api):
        mock_api["patch"].side_effect = _conflict(
            "/organizer/shopping-products/4", "A product named 'Rice' already exists", method="PATCH"
        )
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product(id=4, name="Milk")],
        })

        resp = client.post("/shopping/products/4", data={"name": "Rice", "category_id": "1"})

        assert resp.status_code == 200
        assert "A product named &#39;Rice&#39; already exists" in resp.text or "A product named 'Rice' already exists" in resp.text
        assert 'value="Milk"' in resp.text

    def test_create_product(self, client, mock_api):
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product(name="Rice", default_unit="kg")],
        })

        resp = client.post("/shopping/products", data={"name": "Rice", "category_id": "1", "default_unit": "kg"})

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with(
            "/organizer/shopping-products", json={"name": "Rice", "category_id": 1, "default_unit": "kg"}
        )

    def test_delete_blocked_by_pending_entry_shows_the_message(self, client, mock_api):
        mock_api["delete"].side_effect = _conflict(
            "/organizer/shopping-products/4", "'Milk' is on the shopping list; remove that entry first", method="DELETE"
        )
        mock_api["get"].side_effect = _route_get({
            "/organizer/shopping-categories": [_category()],
            "/organizer/shopping-products": [_product(id=4, pending=True)],
        })

        resp = client.delete("/shopping/products/4")

        assert resp.status_code == 200
        assert "remove that entry first" in resp.text
        assert "on list" in resp.text

    def test_merge_posts_to_the_source_product(self, client, mock_api):
        resp = client.post("/shopping/products/merge", data={"source_id": "4", "into_id": "5"})

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/organizer/shopping-products/4/merge", json={"into_id": 5})

    def test_merge_relays_the_backend_conflict(self, client, mock_api):
        mock_api["post"].side_effect = _conflict("/organizer/shopping-products/4/merge", "both are on the shopping list")

        resp = client.post("/shopping/products/merge", data={"source_id": "4", "into_id": "5"})

        assert resp.status_code == 409
        assert "both are on the shopping list" in resp.text
