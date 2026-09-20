from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.features.core.api_requests.service import ApiRequestService


@pytest.fixture
def service():
    with patch("app.features.core.api_requests.service.ApiRequestRepository") as repo_cls:
        repo_cls.return_value = AsyncMock()
        svc = ApiRequestService(session=AsyncMock())
    return svc


class TestRecord:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("web", "web"),
            ("  N8N ", "n8n"),
            ("MCP", "mcp"),
            (None, "unknown"),
            ("", "unknown"),
            ("   ", "unknown"),
            ("some-typo", "some-typo"),
        ],
    )
    async def test_normalises_client(self, service, raw, expected):
        await service.record(client=raw, method="GET", route="/x", status_code=200, duration_ms=5)

        assert service._repo.create.call_args.kwargs["client"] == expected

    async def test_truncates_overlong_client(self, service):
        await service.record(client="a" * 200, method="GET", route="/x", status_code=200, duration_ms=5)

        assert service._repo.create.call_args.kwargs["client"] == "a" * 50

    async def test_passes_request_fields_to_repo(self, service):
        await service.record(client="web", method="POST", route="/tasks/{id}", status_code=201, duration_ms=12)

        service._repo.create.assert_awaited_once_with(
            client="web", method="POST", route="/tasks/{id}", status_code=201, duration_ms=12
        )


class TestGetSummary:
    async def test_builds_summary_from_repo_rows(self, service):
        service._repo.usage_by_client.return_value = [
            SimpleNamespace(client="web", requests=8, errors=1, avg_latency_ms=20.4),
            SimpleNamespace(client="unknown", requests=2, errors=2, avg_latency_ms=None),
        ]
        service._repo.usage_by_route.return_value = [
            SimpleNamespace(client="web", method="GET", route="/organizer/tasks", requests=5, errors=0),
        ]

        summary = await service.get_summary(days=7)

        assert summary.days == 7
        assert summary.total == 10
        assert [c.client for c in summary.by_client] == ["web", "unknown"]
        assert summary.by_client[0].avg_latency_ms == 20.4
        assert summary.by_client[1].avg_latency_ms == 0.0
        assert summary.top_routes[0].route == "/organizer/tasks"

    async def test_queries_repo_with_window_start(self, service):
        service._repo.usage_by_client.return_value = []
        service._repo.usage_by_route.return_value = []

        before = datetime.now(timezone.utc)
        await service.get_summary(days=3)

        since = service._repo.usage_by_client.call_args.kwargs["since"]
        assert before - timedelta(days=3, seconds=1) <= since <= datetime.now(timezone.utc) - timedelta(days=3) + timedelta(seconds=1)
        assert service._repo.usage_by_route.call_args.kwargs["since"] == since

    async def test_empty_summary(self, service):
        service._repo.usage_by_client.return_value = []
        service._repo.usage_by_route.return_value = []

        summary = await service.get_summary(days=7)

        assert summary.total == 0
        assert summary.by_client == []
        assert summary.top_routes == []
