from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.activities.repository import TAG_PROVIDER_ID, ActivityRepository
from app.features.organizer.activities.schemas import ActivityCreate, ActivityFilters
from app.features.organizer.activities.tables import Activity, ActivityLog
from app.features.organizer.tags.tables import Tag
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper
import app.features.organizer.calendar_events.tables  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _session(rows=None, first=None):
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows or []
    result.scalars.return_value.first.return_value = first
    result.all.return_value = rows or []
    session.execute.return_value = result
    return session


class TestTables:
    def test_log_foreign_key_is_restrict_so_archiving_never_loses_history(self):
        fk = next(iter(ActivityLog.__table__.c.activity_id.foreign_keys))
        assert fk.ondelete == "RESTRICT"

    def test_tag_join_cascades_only_the_link_rows(self):
        join = Tag.activities.property.secondary
        assert {fk.ondelete for fk in join.foreign_keys} == {"CASCADE"}
        assert set(join.c.keys()) == {"activity_id", "tag_id"}

    def test_new_entities_declare_both_timestamps(self):
        for table in (Activity.__table__, ActivityLog.__table__):
            assert {"created_at", "updated_at"} <= set(table.c.keys())
        assert "archived_at" in Activity.__table__.c

    def test_check_constraints_declared(self):
        names = {c.name for c in Activity.__table__.constraints}
        assert {"ck_activities_min_minutes", "ck_activities_max_minutes", "ck_activities_min_max",
                "ck_activities_target_per_week", "ck_activities_context"} <= names
        assert "ck_activity_logs_minutes" in {c.name for c in ActivityLog.__table__.constraints}


class TestQueries:
    async def test_archived_activities_are_hidden_by_default(self):
        session = _session()
        await ActivityRepository(session).get_activities(ActivityFilters())
        assert "activities.archived_at IS NULL" in _sql(session.execute.call_args.args[0])

    async def test_include_archived_drops_the_filter(self):
        session = _session()
        await ActivityRepository(session).get_activities(ActivityFilters(include_archived=True))
        assert "archived_at IS NULL" not in _sql(session.execute.call_args.args[0])

    async def test_tag_and_text_filters(self):
        session = _session()
        await ActivityRepository(session).get_activities(ActivityFilters(tag="Health", q="gy"))
        sql = _sql(session.execute.call_args.args[0])
        assert "lower(organizer.tags.name) = 'health'" in sql
        assert "activities.title ILIKE '%%gy%%'" in sql

    async def test_history_is_newest_first_and_paged(self):
        session = _session()
        await ActivityRepository(session).get_logs(3, limit=10, offset=20)
        sql = _sql(session.execute.call_args.args[0])
        assert "activity_logs.activity_id = 3" in sql
        assert "ORDER BY organizer.activity_logs.done_at DESC" in sql and "LIMIT 10 OFFSET 20" in sql

    async def test_last_done_groups_by_activity(self):
        session = _session(rows=[(1, datetime(2026, 10, 20, 18, 0))])
        assert await ActivityRepository(session).get_last_done([1, 2]) == {1: datetime(2026, 10, 20, 18, 0)}
        assert "max(organizer.activity_logs.done_at)" in _sql(session.execute.call_args.args[0])

    async def test_no_ids_skip_the_queries(self):
        session = _session()
        repo = ActivityRepository(session)
        assert await repo.get_last_done([]) == {}
        assert await repo.count_logs_between([], datetime(2026, 10, 19), datetime(2026, 10, 26)) == {}
        session.execute.assert_not_called()

    async def test_week_counts_use_a_half_open_window(self):
        session = _session(rows=[(1, 2)])
        counts = await ActivityRepository(session).count_logs_between([1], datetime(2026, 10, 19), datetime(2026, 10, 26))
        assert counts == {1: 2}
        sql = _sql(session.execute.call_args.args[0])
        assert "done_at >=" in sql and "done_at <" in sql and "done_at <=" not in sql

    async def test_stats_window_starts_at_the_given_time(self):
        session = _session()
        await ActivityRepository(session).get_logs_since(datetime(2026, 10, 12))
        assert "activity_logs.done_at >=" in _sql(session.execute.call_args.args[0])


class TestTags:
    async def test_new_tags_use_the_fixed_alfred_provider_and_dedupe_case_insensitively(self):
        session = _session(first=None)
        session.execute.side_effect = [
            _session(first=None).execute.return_value,  # lookup "Health"
            _session(first=None).execute.return_value,  # lookup "out"
            _session(first=_activity_with_tags()).execute.return_value,  # re-select after commit
            _session(first=_activity_with_tags()).execute.return_value,
        ]
        repo = ActivityRepository(session)

        await repo.create_activity(ActivityCreate(title="Gym", tags=["Health", "health", " out ", ""]))

        added = [c.args[0] for c in session.add.call_args_list]
        tags = [a for a in added if isinstance(a, Tag)]
        assert [(t.provider_id, t.name) for t in tags] == [(TAG_PROVIDER_ID, "Health"), (TAG_PROVIDER_ID, "out")]


def _activity_with_tags():
    activity = MagicMock()
    activity.id = 1
    return activity
