from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.grammar_scope import handle_grammar_scope


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_scopes = AsyncMock(return_value=[])
    return service


class TestHandleGrammarScopeList:
    async def test_requires_track_id(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_grammar_scope("list", {}, mock_service)
        assert exc_info.value.status_code == 400
        mock_service.get_scopes.assert_not_awaited()

    async def test_lists_scopes_for_track(self, mock_service):
        await handle_grammar_scope("list", {"track_id": "3"}, mock_service)

        called_filters = mock_service.get_scopes.call_args.args[0]
        assert called_filters.track_id == 3
        assert called_filters.status == "ALL"


class TestHandleGrammarScopeUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_grammar_scope("delete", {"track_id": "1"}, mock_service)
        assert exc_info.value.status_code == 400
