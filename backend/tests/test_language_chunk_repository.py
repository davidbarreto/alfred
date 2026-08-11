from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.repository import ChunkRepository
from app.features.language.chunks.schemas import ChunkFilters
from app.features.language.chunks.tables import Chunk, LanguageTag


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _executed_sql(session: AsyncMock) -> str:
    query = session.execute.call_args.args[0]
    return str(query)


def _scalar_first(value) -> MagicMock:
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    return r


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


class TestResolveTags:
    async def test_returns_existing_tag_without_creating(self):
        session = _make_session()
        existing = LanguageTag(id=1, name="Food")
        session.execute.return_value = _scalar_first(existing)

        tags = await ChunkRepository(session)._resolve_tags(["Food"])

        assert tags == [existing]
        session.add.assert_not_called()

    async def test_creates_new_tag_when_missing(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        tags = await ChunkRepository(session)._resolve_tags(["NewGroup"])

        assert len(tags) == 1
        assert tags[0].name == "NewGroup"
        session.add.assert_called_once()

    async def test_empty_list_returns_empty(self):
        session = _make_session()
        tags = await ChunkRepository(session)._resolve_tags([])
        assert tags == []
        session.execute.assert_not_awaited()


class TestApplyFiltersTags:
    def test_tags_filter_uses_any_match(self):
        session = _make_session()
        query = ChunkRepository(session)._apply_filters(
            select(Chunk), ChunkFilters(tags=["Food", "Work"])
        )
        assert "chunks_tags" in str(query)

    def test_untagged_only_excludes_any_tag(self):
        session = _make_session()
        query = ChunkRepository(session)._apply_filters(
            select(Chunk), ChunkFilters(untagged_only=True)
        )
        assert "NOT (EXISTS" in str(query) or "NOT EXISTS" in str(query)

    def test_search_matches_text_or_translation_case_insensitively(self):
        session = _make_session()
        query = ChunkRepository(session)._apply_filters(
            select(Chunk), ChunkFilters(search="Привет")
        )
        sql = str(query)
        assert "lower(language.chunks.text)" in sql
        assert "lower(language.chunks.translation)" in sql

    def test_no_search_omits_ilike(self):
        session = _make_session()
        query = ChunkRepository(session)._apply_filters(select(Chunk), ChunkFilters())
        assert "LIKE" not in str(query).upper()


class TestBulkTagChunks:
    async def test_add_appends_tag_to_chunks_missing_it(self):
        session = _make_session()
        tag = LanguageTag(id=1, name="Food")
        chunk_with_tag = MagicMock(tags=[tag])
        chunk_without_tag = MagicMock(tags=[])
        session.execute.side_effect = [
            _result_with_chunks([chunk_with_tag, chunk_without_tag]),
            _scalar_first(tag),
        ]

        changed = await ChunkRepository(session).bulk_tag_chunks([1, 2], "Food", "add")

        assert changed == 1
        assert tag in chunk_without_tag.tags
        session.commit.assert_awaited_once()

    async def test_add_is_idempotent_when_all_chunks_already_tagged(self):
        session = _make_session()
        tag = LanguageTag(id=1, name="Food")
        chunk = MagicMock(tags=[tag])
        session.execute.side_effect = [_result_with_chunks([chunk]), _scalar_first(tag)]

        changed = await ChunkRepository(session).bulk_tag_chunks([1], "Food", "add")

        assert changed == 0
        session.commit.assert_not_awaited()

    async def test_remove_strips_tag_from_chunks_that_have_it(self):
        session = _make_session()
        tag = LanguageTag(id=1, name="Food")
        chunk_with_tag = MagicMock(tags=[tag])
        chunk_without_tag = MagicMock(tags=[])
        session.execute.side_effect = [
            _result_with_chunks([chunk_with_tag, chunk_without_tag]),
            _scalar_first(tag),
        ]

        changed = await ChunkRepository(session).bulk_tag_chunks([1, 2], "Food", "remove")

        assert changed == 1
        assert tag not in chunk_with_tag.tags
        session.commit.assert_awaited_once()

    async def test_remove_unknown_tag_is_noop(self):
        session = _make_session()
        chunk = MagicMock(tags=[])
        session.execute.side_effect = [_result_with_chunks([chunk]), _scalar_first(None)]

        changed = await ChunkRepository(session).bulk_tag_chunks([1], "Ghost", "remove")

        assert changed == 0
        session.commit.assert_not_awaited()

    async def test_no_matching_chunks_returns_zero_without_querying_tag(self):
        session = _make_session()
        session.execute.return_value = _result_with_chunks([])

        changed = await ChunkRepository(session).bulk_tag_chunks([999], "Food", "add")

        assert changed == 0
        assert session.execute.await_count == 1


class TestTagAwareDueBatch:
    async def test_get_due_chunks_for_track_applies_tag_filter(self):
        session = _make_session()
        session.execute.side_effect = [_result_with_chunks([]), _result_with_chunks([])]
        await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=5, tag_names=["Food"]
        )
        review_sql = str(session.execute.call_args_list[0].args[0])
        assert "chunks_tags" in review_sql

    async def test_get_due_chunks_for_track_applies_states_filter(self):
        session = _make_session()
        session.execute.side_effect = [_result_with_chunks([]), _result_with_chunks([])]
        await ChunkRepository(session).get_due_chunks_for_track(
            track_id=1, limit=5, states=["new"]
        )
        review_sql = str(session.execute.call_args_list[0].args[0])
        assert "state IN" in review_sql

    async def test_count_due_for_track_applies_tag_and_state_filters(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 2
        session.execute.return_value = result_mock

        count = await ChunkRepository(session).count_due_for_track(
            1, tag_names=["Food"], states=["review"]
        )

        assert count == 2
        sql = _executed_sql(session)
        assert "chunks_tags" in sql
        assert "state IN" in sql


class TestTagNamesAndStats:
    async def test_get_tag_names_for_track_returns_distinct_sorted_names(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = ["Food", "Work"]
        session.execute.return_value = result_mock

        names = await ChunkRepository(session).get_tag_names_for_track(1)

        assert names == ["Food", "Work"]

    async def test_get_tag_stats_for_track_shapes_rows(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [("Food", 10, 3, 4.5, 1)]
        session.execute.return_value = result_mock

        stats = await ChunkRepository(session).get_tag_stats_for_track(1)

        assert stats == [{
            "name": "Food",
            "chunk_count": 10,
            "due_count": 3,
            "avg_difficulty": 4.5,
            "leech_count": 1,
        }]

    async def test_get_tag_stats_for_track_handles_null_avg_difficulty(self):
        session = _make_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [("Empty", 0, 0, None, 0)]
        session.execute.return_value = result_mock

        stats = await ChunkRepository(session).get_tag_stats_for_track(1)

        assert stats[0]["avg_difficulty"] == 0.0
