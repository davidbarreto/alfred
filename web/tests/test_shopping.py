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
            "/organizer/shopping/frequent", params={"limit": 15}
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
