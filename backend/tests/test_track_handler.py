from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.track import handle_track


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_tracks = AsyncMock(return_value=[])
    return service


class TestHandleTrackList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_track("list", {}, mock_service)

        called_filters = mock_service.get_tracks.call_args.args[0]
        assert called_filters.active_only is True
        assert called_filters.exclude_paused is False


class TestHandleTrackUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_track("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
