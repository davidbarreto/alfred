from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.repository import ChunkRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _executed_sql(session: AsyncMock) -> str:
    query = session.execute.call_args.args[0]
    return str(query)


def _result_with_chunks(chunks: list) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = chunks
    return result


def _chunk(id_: int, frequency_rank: int | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.id = id_
    chunk.frequency_rank = frequency_rank
    chunk.due_at = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return chunk


class TestShiftDueDates:
    async def test_updates_due_at_and_prod_due_at_for_track(self):
        session = _make_session()
        await ChunkRepository(session).shift_due_dates(1, timedelta(days=3))
        sql = _executed_sql(session)
        assert "due_at" in sql
        assert "prod_due_at" in sql
        assert "track_id" in sql
        assert "status" in sql
        session.commit.assert_awaited_once()


class TestGetDueChunksForTrack:
    async def test_review_chunks_are_never_capped_by_new_cards_limit(self):
        session = _make_session()
        review_chunks = [_chunk(1), _chunk(2)]
        session.execute.side_effect = [
            _result_with_chunks(review_chunks),
            _result_with_chunks([]),
        ]
        result = await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=5, new_cards_limit=0
        )
        assert {c.id for c in result} == {1, 2}

    async def test_new_chunks_fill_remaining_slots_up_to_new_cards_limit(self):
        session = _make_session()
        review_chunks = [_chunk(1)]
        new_chunks = [_chunk(2), _chunk(3), _chunk(4)]
        session.execute.side_effect = [
            _result_with_chunks(review_chunks),
            _result_with_chunks(new_chunks),
        ]
        result = await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=10, new_cards_limit=2
        )
        # new query itself is called with a capped limit, so the mock only
        # returns what the (capped) query would return
        assert {c.id for c in result} == {1, 2, 3, 4}
        new_query_limit = session.execute.call_args_list[1].args[0]._limit_clause.value
        assert new_query_limit == 2

    async def test_no_new_chunks_fetched_when_review_chunks_fill_limit(self):
        session = _make_session()
        review_chunks = [_chunk(1), _chunk(2)]
        session.execute.side_effect = [_result_with_chunks(review_chunks)]
        result = await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=2, new_cards_limit=5
        )
        assert {c.id for c in result} == {1, 2}
        assert session.execute.await_count == 1

    async def test_none_new_cards_limit_means_unthrottled(self):
        session = _make_session()
        review_chunks = [_chunk(1)]
        new_chunks = [_chunk(2)]
        session.execute.side_effect = [
            _result_with_chunks(review_chunks),
            _result_with_chunks(new_chunks),
        ]
        result = await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=5, new_cards_limit=None
        )
        assert {c.id for c in result} == {1, 2}
        new_query_limit = session.execute.call_args_list[1].args[0]._limit_clause.value
        assert new_query_limit == 4


class TestCountNewStartedTodayForTrack:
    async def test_queries_first_reviewed_at_for_track(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 4
        session.execute.return_value = result_mock

        count = await ChunkRepository(session).count_new_started_today_for_track(1)

        assert count == 4
        sql = _executed_sql(session)
        assert "first_reviewed_at" in sql
        assert "track_id" in sql


class TestUpdateSrsFields:
    async def test_omits_first_reviewed_at_when_not_given(self):
        session = _make_session()
        await ChunkRepository(session).update_srs_fields(
            chunk_id=1,
            stability=3.0,
            difficulty=5.0,
            due_at=datetime(2026, 6, 26, tzinfo=timezone.utc),
            last_review_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
            repetitions=1,
            lapses=0,
            consecutive_failures=0,
            state="learning",
            is_leech=False,
        )
        sql = _executed_sql(session)
        assert "first_reviewed_at" not in sql

    async def test_includes_first_reviewed_at_when_given(self):
        session = _make_session()
        await ChunkRepository(session).update_srs_fields(
            chunk_id=1,
            stability=3.0,
            difficulty=5.0,
            due_at=datetime(2026, 6, 26, tzinfo=timezone.utc),
            last_review_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
            repetitions=1,
            lapses=0,
            consecutive_failures=0,
            state="learning",
            is_leech=False,
            first_reviewed_at=datetime(2026, 6, 25, tzinfo=timezone.utc),
        )
        sql = _executed_sql(session)
        assert "first_reviewed_at" in sql
