import logging
from unittest.mock import AsyncMock

import pytest

from app.integrations.leetcode.client import LeetCodeClient


def _page(submissions, has_next=False):
    return {"submissionList": {"hasNext": has_next, "submissions": submissions}}


def _sub(sub_id):
    return {"id": str(sub_id), "titleSlug": "two-sum", "lang": "python3", "statusDisplay": "Accepted", "timestamp": "1700000000"}


@pytest.fixture
def client():
    c = LeetCodeClient(session_cookie="session", csrf_token="csrf")
    c._post = AsyncMock()
    return c


class TestGetSubmissionsSince:
    async def test_returns_only_submissions_newer_than_watermark(self, client):
        client._post.return_value = _page([_sub(30), _sub(20), _sub(10)])
        result = await client.get_submissions_since("15")
        assert [s["id"] for s in result] == ["30", "20"]

    async def test_warns_when_history_is_empty_but_watermark_is_set(self, client, caplog):
        client._post.return_value = _page([])
        with caplog.at_level(logging.WARNING, logger="app.integrations.leetcode.client"):
            result = await client.get_submissions_since("2064098650")
        assert result == []
        assert "session cookie may have expired" in caplog.text

    async def test_no_warning_when_history_is_empty_on_first_sync(self, client, caplog):
        client._post.return_value = _page([])
        with caplog.at_level(logging.WARNING, logger="app.integrations.leetcode.client"):
            await client.get_submissions_since(None)
        assert caplog.text == ""

    async def test_no_warning_when_nothing_is_newer_than_watermark(self, client, caplog):
        client._post.return_value = _page([_sub(10)])
        with caplog.at_level(logging.WARNING, logger="app.integrations.leetcode.client"):
            result = await client.get_submissions_since("10")
        assert result == []
        assert caplog.text == ""
