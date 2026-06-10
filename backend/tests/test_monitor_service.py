import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.features.monitors.service import MonitorService
from app.features.monitors.tables import Monitor


def _make_monitor(**overrides):
    defaults = dict(
        id=1,
        name="Test Monitor",
        description="desc",
        enabled=True,
        type="html_static",
        url="http://example.com",
        selector=".content",
        json_path=None,
        target="Target Text",
        case_sensitive=True,
        timeout=10,
        page_size=32,
        max_pages=None,
        request_delay=0,
        wait_selector=None,
    )
    defaults.update(overrides)
    monitor = MagicMock(spec=Monitor)
    for k, v in defaults.items():
        setattr(monitor, k, v)
    return monitor


# ── check_html_static ─────────────────────────────────────────────────────────

class TestCheckHtmlStatic:
    @patch("app.features.monitors.service.requests.get")
    def test_found_target(self, mock_get):
        mock_get.return_value.text = '<div class="content">Target Text here</div>'
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com", selector=".content", target="Target Text"
        )

        assert result["found"] is True
        assert result["elements_checked"] == 1
        assert result["error"] is None
        assert result["monitor_type"] == "html_static"

    @patch("app.features.monitors.service.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value.text = '<div class="content">Other content</div>'
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com", selector=".content", target="Missing"
        )
        assert result["found"] is False
        assert result["error"] is None

    @patch("app.features.monitors.service.requests.get")
    def test_case_insensitive_found(self, mock_get):
        mock_get.return_value.text = '<div class="content">target text</div>'
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com",
            selector=".content",
            target="Target Text",
            case_sensitive=False,
        )
        assert result["found"] is True

    @patch("app.features.monitors.service.requests.get")
    def test_no_elements_matched(self, mock_get):
        mock_get.return_value.text = "<html><body>no matching selector</body></html>"
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com", selector=".content", target="Target"
        )
        assert result["found"] is False
        assert result["error"] is not None
        assert "No elements" in result["error"]

    @patch("app.features.monitors.service.requests.get")
    def test_request_exception(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("Connection refused")

        result = MonitorService.check_html_static(
            url="http://example.com", selector=".content", target="Target"
        )
        assert result["found"] is False
        assert "Request failed" in result["error"]

    @patch("app.features.monitors.service.requests.get")
    def test_multiple_elements_found_on_first(self, mock_get):
        mock_get.return_value.text = (
            '<div class="content">Target Text</div>'
            '<div class="content">Other</div>'
        )
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com", selector=".content", target="Target Text"
        )
        assert result["found"] is True
        assert result["elements_checked"] == 2

    @patch("app.features.monitors.service.requests.get")
    def test_result_includes_metadata(self, mock_get):
        mock_get.return_value.text = "<html></html>"
        mock_get.return_value.status_code = 200

        result = MonitorService.check_html_static(
            url="http://example.com",
            selector=".none",
            target="Target",
            timeout=30,
        )
        assert result["url"] == "http://example.com"
        assert result["selector"] == ".none"
        assert result["target"] == "Target"
        assert result["timeout"] == 30


# ── check_api ─────────────────────────────────────────────────────────────────

class TestCheckApi:
    @patch("app.integrations.http.pagination.requests.get")
    def test_found_in_content(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "Target Text", "id": 1}],
            "last": True,
            "totalPages": 1,
        }

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="Target Text"
        )
        assert result["found"] is True
        assert result["elements_checked"] == 1

    @patch("app.integrations.http.pagination.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "Other Item"}],
            "last": True,
            "totalPages": 1,
        }

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="Missing"
        )
        assert result["found"] is False

    @patch("app.integrations.http.pagination.requests.get")
    def test_empty_content_sets_error(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [], "last": True, "totalPages": 1
        }

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="Target"
        )
        assert result["found"] is False
        assert result["error"] is not None

    @patch("app.integrations.http.pagination.requests.get")
    def test_case_insensitive(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "target text"}],
            "last": True,
            "totalPages": 1,
        }

        result = MonitorService.check_api(
            url="http://api.example.com",
            json_path="content",
            target="Target Text",
            case_sensitive=False,
        )
        assert result["found"] is True

    @patch("app.integrations.http.pagination.requests.get")
    def test_request_exception(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("Connection error")

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="Target"
        )
        assert result["found"] is False
        assert result["error"] is not None

    @patch("app.integrations.http.pagination.requests.get")
    def test_nested_json_path(self, mock_get):
        mock_get.return_value.json.return_value = {
            "data": {"items": [{"value": "Target Text"}]},
            "last": True,
            "totalPages": 1,
        }

        result = MonitorService.check_api(
            url="http://api.example.com",
            json_path="data.items",
            target="Target Text",
        )
        assert result["found"] is True

    @patch("app.integrations.http.pagination.requests.get")
    def test_recursive_search_in_nested_dict(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"nested": {"deep": "Target Text"}}],
            "last": True,
            "totalPages": 1,
        }

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="Target Text"
        )
        assert result["found"] is True

    @patch("app.integrations.http.pagination.requests.get")
    def test_result_metadata(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [], "last": True, "totalPages": 1
        }

        result = MonitorService.check_api(
            url="http://api.example.com", json_path="content", target="T", timeout=5
        )
        assert result["monitor_type"] == "api"
        assert result["url"] == "http://api.example.com"
        assert result["timeout"] == 5


# ── dispatch_monitor ──────────────────────────────────────────────────────────

class TestDispatchMonitor:
    @patch.object(MonitorService, "check_html_static", return_value={"found": True})
    def test_dispatches_html_static(self, mock_check):
        monitor = _make_monitor(type="html_static", selector=".content")
        result = MonitorService.dispatch_monitor(monitor)

        mock_check.assert_called_once_with(
            url=monitor.url,
            selector=monitor.selector,
            target=monitor.target,
            case_sensitive=monitor.case_sensitive,
            timeout=monitor.timeout,
        )
        assert result == {"found": True}

    @patch.object(MonitorService, "check_html_javascript", return_value={"found": False})
    def test_dispatches_html_javascript(self, mock_check):
        monitor = _make_monitor(type="html_javascript")
        result = MonitorService.dispatch_monitor(monitor)

        mock_check.assert_called_once()

    @patch.object(MonitorService, "check_api", return_value={"found": True})
    def test_dispatches_api(self, mock_check):
        monitor = _make_monitor(type="api", json_path="content", request_delay=100)
        result = MonitorService.dispatch_monitor(monitor)

        mock_check.assert_called_once()
        # request_delay is converted from ms to seconds
        _, kwargs = mock_check.call_args
        assert kwargs.get("request_delay") == pytest.approx(0.1)

    def test_unknown_type_returns_error(self):
        monitor = _make_monitor(type="unknown_type")
        result = MonitorService.dispatch_monitor(monitor)

        assert result["found"] is False
        assert "Unknown monitor type" in result["error"]

    @patch.object(MonitorService, "check_html_static", return_value={"found": False})
    def test_html_static_uses_empty_selector_when_none(self, mock_check):
        monitor = _make_monitor(type="html_static", selector=None)
        MonitorService.dispatch_monitor(monitor)

        _, kwargs = mock_check.call_args
        assert kwargs.get("selector") == ""


# ── run_monitor, run_due, run_monitor_by_id ───────────────────────────────────

class TestRunMonitor:
    @patch("app.features.monitors.service.create_monitor_log")
    @patch.object(MonitorService, "dispatch_monitor")
    async def test_run_monitor_dispatches_and_logs(self, mock_dispatch, mock_log):
        session = AsyncMock()
        monitor = _make_monitor()
        dispatch_result = {"found": True, "elements_checked": 1, "error": None}
        mock_dispatch.return_value = dispatch_result
        mock_log.return_value = MagicMock()

        await MonitorService.run_monitor(session=session, monitor=monitor)

        mock_dispatch.assert_called_once_with(monitor)
        mock_log.assert_called_once_with(
            session=session, monitor=monitor, result=dispatch_result
        )


class TestRunDue:
    @patch("app.features.monitors.service.get_active_monitors")
    @patch.object(MonitorService, "run_monitor")
    async def test_runs_all_active_monitors(self, mock_run, mock_get_active):
        session = AsyncMock()
        monitors = [_make_monitor(id=i) for i in range(3)]
        mock_get_active.return_value = monitors
        mock_run.return_value = MagicMock()

        result = await MonitorService.run_due(session=session)

        mock_get_active.assert_called_once_with(session=session)
        assert mock_run.call_count == 3
        assert len(result) == 3

    @patch("app.features.monitors.service.get_active_monitors")
    @patch.object(MonitorService, "run_monitor")
    async def test_empty_monitors_returns_empty_list(self, mock_run, mock_get_active):
        session = AsyncMock()
        mock_get_active.return_value = []

        result = await MonitorService.run_due(session=session)

        mock_run.assert_not_called()
        assert result == []


class TestRunMonitorById:
    @patch("app.features.monitors.service.get_monitor")
    @patch.object(MonitorService, "run_monitor")
    async def test_runs_when_found(self, mock_run, mock_get):
        session = AsyncMock()
        monitor = _make_monitor()
        mock_get.return_value = monitor
        mock_run.return_value = MagicMock()

        result = await MonitorService.run_monitor_by_id(session=session, monitor_id=1)

        mock_get.assert_called_once_with(session=session, monitor_id=1)
        mock_run.assert_called_once_with(session=session, monitor=monitor)

    @patch("app.features.monitors.service.get_monitor")
    async def test_returns_none_when_not_found(self, mock_get):
        session = AsyncMock()
        mock_get.return_value = None

        result = await MonitorService.run_monitor_by_id(session=session, monitor_id=999)

        assert result is None
