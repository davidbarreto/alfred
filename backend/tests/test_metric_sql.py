"""Compile the metric queries and DDL against the real Postgres dialect (mocked sessions can't catch SQL bugs)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.features.metrics.entries.repository import MetricEntryRepository
from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.series.repository import MetricSeriesRepository
from app.features.metrics.tags.repository import MetricTagRepository
from app.features.metrics.tags.tables import MetricTag, metric_entry_tag_links


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()


def _session() -> AsyncMock:
    session = AsyncMock()
    session.scalars.return_value = MagicMock(all=lambda: [])
    session.execute.return_value = MagicMock(all=lambda: [])
    return session


class TestEntryQueries:
    async def test_tag_filter_matches_case_insensitively(self):
        session = _session()
        await MetricEntryRepository(session).get_entries(tag="Bus")
        sql = _sql(session.scalars.call_args.args[0])
        assert "metrics.entries_tags" in sql and "lower(metrics.tags.name) = 'bus'" in sql

    async def test_no_tag_filter_means_no_tag_join(self):
        session = _session()
        await MetricEntryRepository(session).get_entries()
        assert "entries_tags" not in _sql(session.scalars.call_args.args[0])

    async def test_filters_and_pagination(self):
        session = _session()
        since = datetime(2026, 10, 1, tzinfo=timezone.utc)
        await MetricEntryRepository(session).get_entries(
            series_id=3, status="closed", since=since, limit=20, offset=40
        )
        sql = _sql(session.scalars.call_args.args[0])
        assert "metrics.entries.series_id = 3" in sql and "metrics.entries.status = 'closed'" in sql
        assert "started_at >=" in sql and "limit 20" in sql and "offset 40" in sql
        assert "order by metrics.entries.started_at desc" in sql

    async def test_open_entries_newest_first(self):
        session = _session()
        await MetricEntryRepository(session).get_open_entries(series_id=2)
        sql = _sql(session.scalars.call_args.args[0])
        assert "status = 'open'" in sql and "series_id = 2" in sql and "started_at desc" in sql

    async def test_tag_usage_query_compiles(self):
        session = _session()
        await MetricTagRepository(session).get_tags_with_usage()
        assert "entries_tags" in _sql(session.execute.call_args.args[0])

    async def test_series_listing_hides_archived_and_counts_non_discarded(self):
        session = _session()
        await MetricSeriesRepository(session).get_all_series()
        sql = _sql(session.execute.call_args.args[0])
        assert "is_archived is false" in sql and "status != 'discarded'" in sql


class TestSchemaDefinition:
    def test_every_foreign_key_restricts(self):
        """No cascades anywhere (see the account cascade-delete incident)."""
        foreign_keys = [*MetricEntry.__table__.foreign_keys, *metric_entry_tag_links.foreign_keys]
        assert len(foreign_keys) == 3
        assert {fk.ondelete for fk in foreign_keys} == {"RESTRICT"}

    def test_entries_ddl_compiles_with_constraints(self):
        ddl = str(CreateTable(MetricEntry.__table__).compile(dialect=postgresql.dialect())).lower()
        assert "ck_metric_entries_ended_after_start" in ddl and "ck_metric_entries_status" in ddl
        assert "jsonb" in ddl

    def test_open_entries_index_is_partial(self):
        index = next(i for i in MetricEntry.__table__.indexes if i.name == "ix_metric_entries_open")
        assert "status = 'open'" in str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    def test_tag_names_are_unique_ignoring_case(self):
        index = next(i for i in MetricTag.__table__.indexes if i.name == "uq_metric_tags_name_lower")
        assert index.unique and "lower" in str(CreateIndex(index).compile(dialect=postgresql.dialect())).lower()


class TestStatsQueries:
    @staticmethod
    async def _compile(**kwargs) -> str:
        from app.features.metrics.stats.repository import MetricStatsRepository

        session = _session()
        await MetricStatsRepository(session).get_stats(1, kwargs.pop("kind", "duration"), "Europe/Lisbon", 21600, **kwargs)
        return _sql(session.execute.call_args.args[0])

    async def test_duration_aggregates_derived_seconds_of_closed_entries_under_the_cap(self):
        sql = await self._compile()
        assert "percentile_cont(0.5) within group" in sql and "percentile_cont(0.9) within group" in sql
        assert "extract(epoch from metrics.entries.ended_at - metrics.entries.started_at)" in sql
        assert "metrics.entries.status = 'closed'" in sql and "<= 21600" in sql

    async def test_value_series_aggregate_the_stored_value_without_a_cap(self):
        sql = await self._compile(kind="value")
        assert "metrics.entries.value" in sql and "<= 21600" not in sql

    async def test_hours_and_weekdays_are_taken_in_the_local_timezone(self):
        hour = await self._compile(group_by="hour")
        weekday = await self._compile(group_by="weekday")
        assert "extract(hour from timezone('europe/lisbon'" in hour
        assert "isodow" in weekday and "group by" in weekday

    async def test_weather_groups_use_the_start_snapshot(self):
        sql = await self._compile(group_by="weather")
        assert "context -> 'start'" in sql and "precipitation_mm" in sql
        assert "'unknown'" in sql and "'dry'" in sql and "'rain'" in sql

    async def test_tag_groups_join_the_tag_tables_case_insensitively(self):
        sql = await self._compile(group_by="tag")
        assert "join metrics.tags" in sql and "group by lower(metrics.tags.name)" in sql

    async def test_window_and_tag_filters(self):
        since = datetime(2026, 9, 1, tzinfo=timezone.utc)
        sql = await self._compile(since=since, until=datetime(2026, 10, 1, tzinfo=timezone.utc), tag="Bus")
        assert "started_at >=" in sql and "started_at <" in sql and "lower(metrics.tags.name) = 'bus'" in sql

    async def test_over_cap_count_query(self):
        from app.features.metrics.stats.repository import MetricStatsRepository

        session = _session()
        session.scalar.return_value = 3
        assert await MetricStatsRepository(session).count_over_cap(1, 21600) == 3
        sql = _sql(session.scalar.call_args.args[0])
        assert "> 21600" in sql and "status = 'closed'" in sql
