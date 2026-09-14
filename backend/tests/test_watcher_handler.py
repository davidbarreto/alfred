from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.watcher import handle_alert, handle_watcher


@pytest.fixture
def mock_session():
    return AsyncMock()


class TestHandleWatcherGet:
    async def test_returns_watcher_when_found(self, mock_session):
        watcher = MagicMock()
        with patch(
            "app.assistant.commands.handlers.watcher.get_watcher", AsyncMock(return_value=watcher)
        ), patch(
            "app.assistant.commands.handlers.watcher.WatcherRead.model_validate",
            return_value=MagicMock(model_dump=MagicMock(return_value={"id": 1})),
        ):
            result = await handle_watcher("get", {"id": "1"}, mock_session)

        assert result == {"id": 1}

    async def test_raises_404_when_not_found(self, mock_session):
        with patch("app.assistant.commands.handlers.watcher.get_watcher", AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await handle_watcher("get", {"id": "999"}, mock_session)
        assert exc_info.value.status_code == 404


class TestHandleWatcherList:
    async def test_lists_watchers(self, mock_session):
        with patch("app.assistant.commands.handlers.watcher.get_watchers", AsyncMock(return_value=[])) as mock_get:
            result = await handle_watcher("list", {}, mock_session)

        mock_get.assert_awaited_once_with(session=mock_session, limit=100)
        assert result == []

    async def test_unknown_command_raises_400(self, mock_session):
        with pytest.raises(HTTPException) as exc_info:
            await handle_watcher("delete", {}, mock_session)
        assert exc_info.value.status_code == 400


class TestHandleAlertList:
    async def test_lists_alerts_with_filters(self, mock_session):
        with patch("app.assistant.commands.handlers.watcher.get_alerts", AsyncMock(return_value=[])) as mock_get:
            result = await handle_alert("list", {"status": "pending", "config_id": "5"}, mock_session)

        mock_get.assert_awaited_once_with(session=mock_session, status="pending", config_id=5, limit=20)
        assert result == []

    async def test_unknown_command_raises_400(self, mock_session):
        with pytest.raises(HTTPException) as exc_info:
            await handle_alert("resolve", {}, mock_session)
        assert exc_info.value.status_code == 400
