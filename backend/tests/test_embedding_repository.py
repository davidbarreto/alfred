from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import InvalidRequestError

from app.features.core.embeddings.repository import EmbeddingRepository


def _session(existing=None) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    session.execute = AsyncMock(return_value=result)
    return session


def _upsert_kwargs() -> dict:
    return dict(
        source_type="visit_note",
        source_id=1,
        content="Visit to X: nice",
        vector=[0.1] * 4,
        model="m",
        dimensions=4,
    )


class TestUpsertRefresh:
    @pytest.mark.asyncio
    async def test_insert_refreshes_by_default(self):
        session = _session()

        await EmbeddingRepository(session).upsert(**_upsert_kwargs())

        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_refreshes_by_default(self):
        session = _session(existing=MagicMock())

        await EmbeddingRepository(session).upsert(**_upsert_kwargs())

        session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_without_refresh_survives_a_concurrent_delete(self):
        """A delete landing between commit and refresh makes refresh() raise; callers that
        discard the row (background indexing) opt out of the refresh entirely."""
        session = _session()
        session.refresh = AsyncMock(side_effect=InvalidRequestError("Could not refresh instance"))

        await EmbeddingRepository(session).upsert(**_upsert_kwargs(), refresh=False)

        session.commit.assert_awaited_once()
        session.refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_without_refresh_survives_a_concurrent_delete(self):
        session = _session(existing=MagicMock())
        session.refresh = AsyncMock(side_effect=InvalidRequestError("Could not refresh instance"))

        await EmbeddingRepository(session).upsert(**_upsert_kwargs(), refresh=False)

        session.commit.assert_awaited_once()
        session.refresh.assert_not_awaited()
