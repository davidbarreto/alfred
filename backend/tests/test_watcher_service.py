import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.features.watcher.service import WatcherService, _derive_status
from app.features.watcher.tables import Watcher


def _make_watcher(**overrides):
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
    watcher = MagicMock(spec=Watcher)
    for k, v in defaults.items():
        setattr(watcher, k, v)
    return watcher


# ── _derive_status ────────────────────────────────────────────────────────────

class TestDeriveStatus:
    def test_found(self):
        status, result, error = _derive_status({"found": True, "matched_content": "hello", "error": None})
        assert status == "found"
        assert result == "hello"
        assert error is None

    def test_not_found(self):
        status, result, error = _derive_status({"found": False, "matched_content": None, "error": None})
        assert status == "not_found"
        assert result is None
        assert error is None

    def test_error_takes_precedence(self):
        status, result, error = _derive_status({"found": False, "matched_content": None, "error": "Request failed"})
        assert status == "error"
        assert result is None
        assert error == "Request failed"

    def test_found_returns_matched_content(self):
        status, result, error = _derive_status({"found": True, "matched_content": "the text", "error": None})
        assert result == "the text"


# ── check_html_static ─────────────────────────────────────────────────────────

class TestCheckHtmlStatic:
    @patch("app.features.monitoring.service.requests.get")
    def test_found_target(self, mock_get):
        mock_get.return_value.text = '<div class="content">Target Text here</div>'
        mock_get.return_value.status_code = 200

        result = WatcherService.check_html_static(
            url="http://example.com", selector=".content", target="Target Text"
        )

        assert result["found"] is True
        assert result["matched_content"] is not None
        assert "Target Text" in result["matched_content"]
        assert result["error"] is None

    @patch("app.features.monitoring.service.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value.text = '<div class="content">Other content</div>'
        mock_get.return_value.status_code = 200

        result = WatcherService.check_html_static(
            url="http://example.com", selector=".content", target="Missing"
        )
        assert result["found"] is False
        assert result["matched_content"] is None
        assert result["error"] is None

    @patch("app.features.monitoring.service.requests.get")
    def test_case_insensitive_found(self, mock_get):
        mock_get.return_value.text = '<div class="content">target text</div>'
        mock_get.return_value.status_code = 200

        result = WatcherService.check_html_static(
            url="http://example.com",
            selector=".content",
            target="Target Text",
            case_sensitive=False,
        )
        assert result["found"] is True

    @patch("app.features.monitoring.service.requests.get")
    def test_no_elements_matched(self, mock_get):
        mock_get.return_value.text = "<html><body>no matching selector</body></html>"
        mock_get.return_value.status_code = 200

        result = WatcherService.check_html_static(
            url="http://example.com", selector=".content", target="Target"
        )
        assert result["found"] is False
        assert result["error"] is not None
        assert "No elements" in result["error"]

    @patch("app.features.monitoring.service.requests.get")
    def test_request_exception(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("Connection refused")

        result = WatcherService.check_html_static(
            url="http://example.com", selector=".content", target="Target"
        )
        assert result["found"] is False
        assert "Request failed" in result["error"]

    @patch("app.features.monitoring.service.requests.get")
    def test_matched_content_truncated_at_500_chars(self, mock_get):
        long_text = "Target Text " + "x" * 600
        mock_get.return_value.text = f'<div class="content">{long_text}</div>'
        mock_get.return_value.status_code = 200

        result = WatcherService.check_html_static(
            url="http://example.com", selector=".content", target="Target Text"
        )
        assert result["found"] is True
        assert len(result["matched_content"]) <= 500


# ── check_api ─────────────────────────────────────────────────────────────────

class TestCheckApi:
    @patch("app.integrations.http.pagination.requests.get")
    def test_found_in_content(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "Target Text", "id": 1}],
            "last": True,
            "totalPages": 1,
        }

        result = WatcherService.check_api(
            url="http://api.example.com", json_path="content", target="Target Text"
        )
        assert result["found"] is True
        assert result["matched_content"] is not None

    @patch("app.integrations.http.pagination.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "Other Item"}],
            "last": True,
            "totalPages": 1,
        }

        result = WatcherService.check_api(
            url="http://api.example.com", json_path="content", target="Missing"
        )
        assert result["found"] is False
        assert result["matched_content"] is None

    @patch("app.integrations.http.pagination.requests.get")
    def test_empty_content_sets_error(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [], "last": True, "totalPages": 1
        }

        result = WatcherService.check_api(
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

        result = WatcherService.check_api(
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

        result = WatcherService.check_api(
            url="http://api.example.com", json_path="content", target="Target"
        )
        assert result["found"] is False
        assert result["error"] is not None

    @patch("app.integrations.http.pagination.requests.get")
    def test_recursive_search_in_nested_dict(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"nested": {"deep": "Target Text"}}],
            "last": True,
            "totalPages": 1,
        }

        result = WatcherService.check_api(
            url="http://api.example.com", json_path="content", target="Target Text"
        )
        assert result["found"] is True

    @patch("app.integrations.http.pagination.requests.get")
    def test_matched_content_is_string(self, mock_get):
        mock_get.return_value.json.return_value = {
            "content": [{"name": "Target Text"}],
            "last": True,
            "totalPages": 1,
        }

        result = WatcherService.check_api(
            url="http://api.example.com", json_path="content", target="Target Text"
        )
        assert isinstance(result["matched_content"], str)


# ── dispatch_watcher ──────────────────────────────────────────────────────────

class TestDispatchWatcher:
    @patch.object(MonitorService, "check_html_static", return_value={"found": True, "matched_content": "x", "error": None})
    def test_dispatches_html_static(self, mock_check):
        monitor = _make_watcher(type="html_static", selector=".content")
        result = WatcherService.dispatch_watcher(monitor)

        mock_check.assert_called_once_with(
            url=monitor.url,
            selector=monitor.selector,
            target=monitor.target,
            case_sensitive=monitor.case_sensitive,
            timeout=monitor.timeout,
        )
        assert result["found"] is True

    @patch.object(MonitorService, "check_html_javascript", return_value={"found": False, "matched_content": None, "error": None})
    def test_dispatches_html_javascript(self, mock_check):
        monitor = _make_watcher(type="html_javascript")
        WatcherService.dispatch_watcher(monitor)
        mock_check.assert_called_once()

    @patch.object(MonitorService, "check_api", return_value={"found": True, "matched_content": "x", "error": None})
    def test_dispatches_api(self, mock_check):
        monitor = _make_watcher(type="api", json_path="content", request_delay=100)
        WatcherService.dispatch_watcher(monitor)

        mock_check.assert_called_once()
        _, kwargs = mock_check.call_args
        assert kwargs.get("request_delay") == pytest.approx(0.1)

    def test_unknown_type_returns_error(self):
        monitor = _make_watcher(type="unknown_type")
        result = WatcherService.dispatch_watcher(monitor)

        assert result["found"] is False
        assert "Unknown monitor type" in result["error"]

    @patch.object(MonitorService, "check_html_static", return_value={"found": False, "matched_content": None, "error": None})
    def test_html_static_uses_empty_selector_when_none(self, mock_check):
        monitor = _make_watcher(type="html_static", selector=None)
        WatcherService.dispatch_watcher(monitor)

        _, kwargs = mock_check.call_args
        assert kwargs.get("selector") == ""


# ── run_watcher, run_due, run_watcher_by_id ───────────────────────────────────

class TestRunWatcher:
    @patch("app.features.monitoring.service.upsert_alert")
    @patch("app.features.monitoring.service.create_execution")
    @patch.object(MonitorService, "dispatch_watcher")
    async def test_found_creates_execution_and_alert(self, mock_dispatch, mock_create, mock_alert):
        session = AsyncMock()
        monitor = _make_watcher()
        mock_dispatch.return_value = {"found": True, "matched_content": "match", "error": None}
        execution = MagicMock()
        mock_create.return_value = execution

        await WatcherService.run_watcher(session=session, monitor=monitor)

        mock_create.assert_called_once_with(
            session=session, monitor=monitor, status="found", result="match", error=None
        )
        mock_alert.assert_called_once_with(session=session, execution=execution)

    @patch("app.features.monitoring.service.upsert_alert")
    @patch("app.features.monitoring.service.create_execution")
    @patch.object(MonitorService, "dispatch_watcher")
    async def test_not_found_skips_alert(self, mock_dispatch, mock_create, mock_alert):
        session = AsyncMock()
        monitor = _make_watcher()
        mock_dispatch.return_value = {"found": False, "matched_content": None, "error": None}
        mock_create.return_value = MagicMock()

        await WatcherService.run_watcher(session=session, monitor=monitor)

        mock_create.assert_called_once_with(
            session=session, monitor=monitor, status="not_found", result=None, error=None
        )
        mock_alert.assert_not_called()

    @patch("app.features.monitoring.service.upsert_alert")
    @patch("app.features.monitoring.service.create_execution")
    @patch.object(MonitorService, "dispatch_watcher")
    async def test_error_skips_alert(self, mock_dispatch, mock_create, mock_alert):
        session = AsyncMock()
        monitor = _make_watcher()
        mock_dispatch.return_value = {"found": False, "matched_content": None, "error": "Timeout"}
        mock_create.return_value = MagicMock()

        await WatcherService.run_watcher(session=session, monitor=monitor)

        mock_create.assert_called_once_with(
            session=session, monitor=monitor, status="error", result=None, error="Timeout"
        )
        mock_alert.assert_not_called()


class TestRunDue:
    @patch("app.features.monitoring.service.get_active_monitors")
    @patch.object(MonitorService, "run_watcher")
    async def test_runs_all_active_monitors(self, mock_run, mock_get_active):
        session = AsyncMock()
        monitors = [_make_watcher(id=i) for i in range(3)]
        mock_get_active.return_value = monitors
        mock_run.return_value = MagicMock()

        result = await WatcherService.run_due(session=session)

        mock_get_active.assert_called_once_with(session=session)
        assert mock_run.call_count == 3
        assert len(result) == 3

    @patch("app.features.monitoring.service.get_active_monitors")
    @patch.object(MonitorService, "run_watcher")
    async def test_empty_monitors_returns_empty_list(self, mock_run, mock_get_active):
        session = AsyncMock()
        mock_get_active.return_value = []

        result = await WatcherService.run_due(session=session)

        mock_run.assert_not_called()
        assert result == []


class TestRunWatcherById:
    @patch("app.features.monitoring.service.get_monitor")
    @patch.object(MonitorService, "run_watcher")
    async def test_runs_when_found(self, mock_run, mock_get):
        session = AsyncMock()
        monitor = _make_watcher()
        mock_get.return_value = monitor
        mock_run.return_value = MagicMock()

        await WatcherService.run_watcher_by_id(session=session, monitor_id=1)

        mock_get.assert_called_once_with(session=session, monitor_id=1)
        mock_run.assert_called_once_with(session=session, monitor=monitor)

    @patch("app.features.monitoring.service.get_monitor")
    async def test_returns_none_when_not_found(self, mock_get):
        session = AsyncMock()
        mock_get.return_value = None

        result = await WatcherService.run_watcher_by_id(session=session, monitor_id=999)

        assert result is None
