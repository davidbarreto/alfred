import httpx


def _item(id=1, name="Milk", category="grocery", status="pending"):
    return {"id": id, "name": name, "category": category, "status": status,
             "priority": "need", "quantity": None, "unit": None, "brand": None,
             "estimated_price": None, "source": "manual"}


class TestAddShoppingItem:
    def test_creates_item_and_renders_updated_list(self, client, mock_api):
        mock_api["post"].return_value = _item()
        mock_api["get"].return_value = [_item()]

        resp = client.post("/shopping/", data={"name": "Milk", "category": "grocery", "priority": "need"})

        assert resp.status_code == 200
        assert "Milk" in resp.text
        mock_api["post"].assert_any_await("/organizer/shopping", json={
            "name": "Milk", "category": "grocery", "priority": "need", "source": "manual",
        })
        mock_api["get"].assert_any_await(
            "/organizer/shopping", params={"status": "pending", "category": "all", "limit": 100}
        )
        mock_api["get"].assert_any_await(
            "/organizer/shopping/frequent", params={"limit": 15}
        )

    def test_creates_item_with_optional_fields(self, client, mock_api):
        mock_api["post"].return_value = _item()
        mock_api["get"].return_value = [_item()]

        resp = client.post("/shopping/", data={
            "name": "Milk", "category": "grocery", "priority": "need",
            "quantity": "2", "unit": "L", "estimated_price": "3.50",
            "brand": "Nesquik", "store": "Lidl", "url": "https://example.com/milk",
            "notes": "Lactose-free",
        })

        assert resp.status_code == 200
        mock_api["post"].assert_any_await("/organizer/shopping", json={
            "name": "Milk", "category": "grocery", "priority": "need", "source": "manual",
            "quantity": "2", "unit": "L", "estimated_price": "3.50",
            "brand": "Nesquik", "store": "Lidl", "url": "https://example.com/milk",
            "notes": "Lactose-free",
        })

    def test_returns_422_when_backend_create_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/shopping")
        mock_api["post"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.post("/shopping/", data={"name": "Milk"})

        assert resp.status_code == 422


class TestShoppingPage:
    def test_renders_api_error_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/organizer/shopping")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/shopping/")

        assert resp.status_code == 200
        assert "Cannot reach backend" in resp.text


class TestAddWishlistItem:
    def test_creates_item_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].return_value = [{"id": 1, "name": "Headphones", "category": "electronics",
                                          "brand": None, "estimated_price": None}]

        resp = client.post("/shopping/wishlist", data={"name": "Headphones", "category": "electronics"})

        assert resp.status_code == 200
        assert "Headphones" in resp.text
        mock_api["post"].assert_awaited_once_with(
            "/organizer/wishlist", json={"name": "Headphones", "category": "electronics"}
        )
