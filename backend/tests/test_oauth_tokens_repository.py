from unittest.mock import AsyncMock

import pytest

from app.integrations.oauth_tokens.repository import delete_oauth_token


class TestDeleteOauthToken:

    @pytest.mark.asyncio
    async def test_executes_delete_and_commits(self):
        session = AsyncMock()

        await delete_oauth_token(session, "google_contacts")

        session.execute.assert_awaited_once()
        session.commit.assert_awaited_once()
