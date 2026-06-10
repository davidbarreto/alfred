import pytest
from unittest.mock import patch, MagicMock, call
from app.integrations.http.pagination import _get_nested, fetch_page, paginate, fetch_all


class TestGetNested:
    def test_flat_key(self):
        assert _get_nested({"key": "value"}, "key") == "value"

    def test_nested_two_levels(self):
        data = {"meta": {"page": 1}}
        assert _get_nested(data, "meta.page") == 1

    def test_nested_three_levels(self):
        data = {"meta": {"pagination": {"isLast": True}}}
        assert _get_nested(data, "meta.pagination.isLast") is True

    def test_missing_key_returns_default_none(self):
        assert _get_nested({"key": "value"}, "missing") is None

    def test_missing_key_returns_custom_default(self):
        assert _get_nested({}, "missing", default="fallback") == "fallback"

    def test_empty_path_returns_whole_dict(self):
        data = {"key": "value"}
        assert _get_nested(data, "") == data

    def test_non_dict_intermediate_returns_default(self):
        data = {"key": "string_not_dict"}
        assert _get_nested(data, "key.nested") is None

    def test_nested_value_is_none_returns_default(self):
        data = {"meta": {"page": None}}
        assert _get_nested(data, "meta.page") is None

    def test_integer_value(self):
        assert _get_nested({"count": 42}, "count") == 42

    def test_list_value(self):
        assert _get_nested({"items": [1, 2, 3]}, "items") == [1, 2, 3]


class TestFetchPage:
    @patch("app.integrations.http.pagination.requests.get")
    def test_returns_json(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": ["item"], "last": True}
        mock_get.return_value = mock_response

        result = fetch_page("http://example.com", page=0, page_size=10)
        assert result == {"content": ["item"], "last": True}

    @patch("app.integrations.http.pagination.requests.get")
    def test_sends_correct_params(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        fetch_page("http://example.com", page=2, page_size=50)
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["page"] == 2
        assert kwargs["params"]["size"] == 50

    @patch("app.integrations.http.pagination.requests.get")
    def test_forwards_extra_kwargs(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {}
        mock_get.return_value = mock_response

        fetch_page("http://example.com", page=0, page_size=10, storeId=123)
        _, kwargs = mock_get.call_args
        assert kwargs["params"]["storeId"] == 123

    @patch("app.integrations.http.pagination.requests.get")
    def test_raises_on_http_error(self, mock_get):
        import requests as requests_lib
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests_lib.HTTPError("404")
        mock_get.return_value = mock_response

        with pytest.raises(requests_lib.HTTPError):
            fetch_page("http://example.com", page=0)


class TestPaginate:
    @patch("app.integrations.http.pagination.requests.get")
    def test_single_page(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": ["item1", "item2"],
            "last": True,
            "totalPages": 1,
        }
        mock_get.return_value = mock_response

        pages = list(paginate("http://example.com"))
        assert len(pages) == 1
        assert pages[0] == ["item1", "item2"]

    @patch("app.integrations.http.pagination.requests.get")
    def test_multiple_pages(self, mock_get):
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = {"content": ["a"], "last": False, "totalPages": 2}
        r2.json.return_value = {"content": ["b"], "last": True, "totalPages": 2}
        mock_get.side_effect = [r1, r2]

        pages = list(paginate("http://example.com"))
        assert len(pages) == 2
        assert pages[0] == ["a"]
        assert pages[1] == ["b"]

    @patch("app.integrations.http.pagination.requests.get")
    def test_max_pages_cap(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": ["item"],
            "last": False,
            "totalPages": 100,
        }
        mock_get.return_value = mock_response

        pages = list(paginate("http://example.com", max_pages=3))
        assert len(pages) == 3

    @patch("app.integrations.http.pagination.requests.get")
    def test_stops_at_total_pages(self, mock_get):
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = {"content": ["a"], "last": False, "totalPages": 2}
        r2.json.return_value = {"content": ["b"], "last": False, "totalPages": 2}
        mock_get.side_effect = [r1, r2]

        pages = list(paginate("http://example.com"))
        assert len(pages) == 2

    @patch("app.integrations.http.pagination.requests.get")
    def test_custom_content_key(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {"results": ["item"]},
            "last": True,
            "totalPages": 1,
        }
        mock_get.return_value = mock_response

        pages = list(paginate("http://example.com", content_key="data.results"))
        assert pages[0] == ["item"]

    @patch("app.integrations.http.pagination.requests.get")
    def test_empty_content(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [], "last": True, "totalPages": 1}
        mock_get.return_value = mock_response

        pages = list(paginate("http://example.com"))
        assert pages == [[]]

    @patch("app.integrations.http.pagination.time.sleep")
    @patch("app.integrations.http.pagination.requests.get")
    def test_delay_between_pages(self, mock_get, mock_sleep):
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = {"content": ["a"], "last": False, "totalPages": 2}
        r2.json.return_value = {"content": ["b"], "last": True, "totalPages": 2}
        mock_get.side_effect = [r1, r2]

        list(paginate("http://example.com", delay=0.5))
        mock_sleep.assert_called_once_with(0.5)


class TestFetchAll:
    @patch("app.integrations.http.pagination.requests.get")
    def test_combines_all_pages(self, mock_get):
        r1, r2 = MagicMock(), MagicMock()
        r1.json.return_value = {"content": ["a", "b"], "last": False, "totalPages": 2}
        r2.json.return_value = {"content": ["c"], "last": True, "totalPages": 2}
        mock_get.side_effect = [r1, r2]

        result = fetch_all("http://example.com")
        assert result == ["a", "b", "c"]

    @patch("app.integrations.http.pagination.requests.get")
    def test_empty_result(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [], "last": True, "totalPages": 1}
        mock_get.return_value = mock_response

        result = fetch_all("http://example.com")
        assert result == []

    @patch("app.integrations.http.pagination.requests.get")
    def test_single_page(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": ["x", "y", "z"],
            "last": True,
            "totalPages": 1,
        }
        mock_get.return_value = mock_response

        result = fetch_all("http://example.com")
        assert result == ["x", "y", "z"]
