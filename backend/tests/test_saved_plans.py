from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun import freeze_time
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.planning.saved_plans.repository import DayPlanRepository
from app.features.planning.saved_plans.schemas import DayPlanEdit, DayPlanSave, DayPlansEdit, DayPlansSave, PlanBlock
from app.features.planning.saved_plans.service import (
    SavedPlanConflictError,
    SavedPlanNotFoundError,
    SavedPlanService,
    SavedPlanValidationError,
)
from app.features.planning.saved_plans.tables import DayPlan
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper
import app.features.organizer.calendar_events.tables  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper

_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def _block(start="2026-10-21T18:00:00+01:00", end="2026-10-21T19:00:00+01:00", kind="task", ref_id=None, title="Block", **kw):
    return {"start": start, "end": end, "kind": kind, "ref_id": ref_id, "title": title, **kw}


def _save(*days) -> DayPlansSave:
    return DayPlansSave.model_validate({"days": list(days)})


def _day(day="2026-10-21", items=None, notes=None):
    return {"date": day, "items": items if items is not None else [_block()], "notes": notes}


def _row(plan_date=date(2026, 10, 21), version=1, items=None, archived_at=None, **kw):
    defaults = dict(
        id=1, plan_date=plan_date, version=version, items=items or [], notes=None, source="mcp",
        created_at=_NOW, updated_at=_NOW, archived_at=archived_at,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestPlanBlock:
    def test_valid_block(self):
        block = PlanBlock(**_block(kind="event", ref_id=4))
        assert block.start.utcoffset().total_seconds() == 3600

    @pytest.mark.parametrize("field", ["start", "end"])
    def test_datetimes_need_an_offset(self, field):
        with pytest.raises(ValidationError, match="UTC offset"):
            PlanBlock(**_block(**{field: "2026-10-21T18:00:00"}))

    def test_end_may_equal_start_but_not_precede_it(self):
        PlanBlock(**_block(end="2026-10-21T18:00:00+01:00"))
        with pytest.raises(ValidationError):
            PlanBlock(**_block(end="2026-10-21T17:00:00+01:00"))

    @pytest.mark.parametrize("kind", ["work", "transport"])
    def test_work_and_transport_are_valid_free_form_kinds(self, kind):
        assert PlanBlock(**_block(kind=kind)).kind == kind
        with pytest.raises(ValidationError, match="ref_id"):
            PlanBlock(**_block(kind=kind, ref_id=3))

    @pytest.mark.parametrize("kind", ["meal", "break", "other"])
    def test_free_form_kinds_take_no_ref(self, kind):
        with pytest.raises(ValidationError, match="ref_id"):
            PlanBlock(**_block(kind=kind, ref_id=3))

    def test_unknown_kind_and_blank_title_rejected(self):
        with pytest.raises(ValidationError):
            PlanBlock(**_block(kind="meeting"))
        with pytest.raises(ValidationError):
            PlanBlock(**_block(title=""))

    def test_save_needs_at_least_one_day_and_at_most_31(self):
        with pytest.raises(ValidationError):
            DayPlansSave(days=[])
        with pytest.raises(ValidationError):
            DayPlansSave(days=[DayPlanSave(date=date(2026, 10, 1), items=[])] * 32)


class TestTable:
    def test_one_active_plan_per_date_is_enforced_by_a_partial_unique_index(self):
        index = next(i for i in DayPlan.__table__.indexes if i.name == "uq_day_plans_active_date")
        assert index.unique is True
        assert [c.name for c in index.columns] == ["plan_date"]
        assert "archived_at IS NULL" in str(index.dialect_options["postgresql"]["where"])

    def test_versions_are_unique_per_date_and_source_is_checked(self):
        names = {c.name for c in DayPlan.__table__.constraints}
        assert {"uq_day_plans_date_version", "ck_day_plans_source", "ck_day_plans_version"} <= names

    def test_new_entity_declares_both_timestamps(self):
        assert {"created_at", "updated_at", "archived_at"} <= set(DayPlan.__table__.c.keys())


@pytest.fixture
def repo_mock():
    repo = AsyncMock()
    repo.existing_ref_ids.side_effect = lambda kind, ids: set(ids)
    repo.save_days.side_effect = lambda entries, source: [
        _row(plan_date=d, version=2, items=items, notes=notes, source=source) for d, items, notes in entries
    ]
    return repo


@pytest.fixture
def service(repo_mock):
    svc = SavedPlanService(session=AsyncMock())
    svc._repo = repo_mock
    return svc


class TestSave:
    async def test_saves_blocks_sorted_with_offsets_and_the_source(self, service, repo_mock):
        data = _save(_day(items=[
            _block("2026-10-21T20:00:00+01:00", "2026-10-21T21:00:00+01:00", title="Late"),
            _block("2026-10-21T09:00:00+01:00", "2026-10-21T10:00:00+01:00", title="Early"),
        ], notes="Light day"))

        plans = await service.save(data, "mcp")

        entries, source = repo_mock.save_days.call_args.args
        assert source == "mcp"
        plan_date, items, notes = entries[0]
        assert plan_date == date(2026, 10, 21) and notes == "Light day"
        assert [i["title"] for i in items] == ["Early", "Late"]
        assert items[0]["start"] == "2026-10-21T09:00:00+01:00"
        assert plans[0].items[0].title == "Early"

    async def test_offsets_are_normalised_to_the_local_zone(self, service, repo_mock):
        await service.save(_save(_day(items=[_block("2026-10-21T17:00:00+00:00", "2026-10-21T18:00:00+00:00")])), "mcp")
        item = repo_mock.save_days.call_args.args[0][0][1][0]
        assert (item["start"], item["end"]) == ("2026-10-21T18:00:00+01:00", "2026-10-21T19:00:00+01:00")

    async def test_each_date_gets_its_own_entry_and_other_dates_are_not_touched(self, service, repo_mock):
        data = _save(
            _day("2026-10-21"),
            _day("2026-10-22", [_block("2026-10-22T09:00:00+01:00", "2026-10-22T10:00:00+01:00")]),
            _day("2026-10-23", [_block("2026-10-23T09:00:00+01:00", "2026-10-23T10:00:00+01:00")]),
        )
        await service.save(data, "portal")
        entries = repo_mock.save_days.call_args.args[0]
        assert [e[0] for e in entries] == [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]
        repo_mock.save_days.assert_awaited_once()

    async def test_repeated_date_in_one_call_is_rejected(self, service, repo_mock):
        with pytest.raises(SavedPlanValidationError, match="2026-10-21"):
            await service.save(_save(_day(), _day()), "mcp")
        repo_mock.save_days.assert_not_called()

    async def test_unknown_ref_id_is_rejected_and_nothing_is_saved(self, service, repo_mock):
        repo_mock.existing_ref_ids.side_effect = lambda kind, ids: set()
        data = _save(_day(items=[_block(kind="task", ref_id=999)]))
        with pytest.raises(SavedPlanValidationError, match=r"Unknown task ref_id\(s\): 999"):
            await service.save(data, "mcp")
        repo_mock.save_days.assert_not_called()

    async def test_refs_are_checked_per_kind(self, service, repo_mock):
        data = _save(_day(items=[
            _block(kind="event", ref_id=1), _block(kind="task", ref_id=2), _block(kind="task", ref_id=3),
            _block(kind="study_item", ref_id=4), _block(kind="routine_step", ref_id=5),
            _block(kind="break"), _block(kind="task"),
        ]))
        await service.save(data, "mcp")
        checked = {c.args[0]: c.args[1] for c in repo_mock.existing_ref_ids.call_args_list}
        assert checked == {"event": {1}, "task": {2, 3}, "study_item": {4}, "routine_step": {5}}

    async def test_only_missing_ids_are_named(self, service, repo_mock):
        repo_mock.existing_ref_ids.side_effect = lambda kind, ids: {i for i in ids if i != 3}
        data = _save(_day(items=[_block(kind="event", ref_id=2), _block(kind="event", ref_id=3)]))
        with pytest.raises(SavedPlanValidationError, match=r"Unknown event ref_id\(s\): 3$"):
            await service.save(data, "mcp")

    async def test_block_starting_on_another_date_is_rejected(self, service, repo_mock):
        data = _save(_day("2026-10-21", [_block("2026-10-22T09:00:00+01:00", "2026-10-22T10:00:00+01:00", title="Misfiled")]))
        with pytest.raises(SavedPlanValidationError, match="Misfiled.*2026-10-22.*2026-10-21"):
            await service.save(data, "mcp")

    async def test_date_check_uses_the_local_zone_not_utc(self, service, repo_mock):
        # 23:30 UTC on the 20th is 00:30 on the 21st in Lisbon (WEST)
        data = _save(_day("2026-10-21", [_block("2026-10-20T23:30:00+00:00", "2026-10-21T00:30:00+00:00")]))
        await service.save(data, "mcp")
        repo_mock.save_days.assert_awaited_once()

    async def test_block_crossing_midnight_stays_on_its_start_date(self, service, repo_mock):
        data = _save(_day(items=[_block("2026-10-21T23:00:00+01:00", "2026-10-22T07:00:00+01:00", kind="other", title="Sleep")]))
        await service.save(data, "mcp")
        repo_mock.save_days.assert_awaited_once()

    async def test_a_concurrent_save_is_a_conflict(self, service, repo_mock):
        repo_mock.save_days.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        with pytest.raises(SavedPlanConflictError):
            await service.save(_save(_day()), "mcp")

    async def test_empty_day_can_be_saved(self, service, repo_mock):
        await service.save(_save(_day(items=[], notes="Day off")), "mcp")
        assert repo_mock.save_days.call_args.args[0][0][1] == []


class TestRead:
    async def test_week_returns_every_active_plan(self, service, repo_mock):
        repo_mock.get_active_plans.return_value = [_row(plan_date=date(2026, 10, 19 + i)) for i in range(7)]
        plans = await service.get_saved(date(2026, 10, 19), date(2026, 10, 25))
        assert [p.plan_date.day for p in plans] == list(range(19, 26))
        repo_mock.get_active_plans.assert_awaited_once_with(date(2026, 10, 19), date(2026, 10, 25))

    async def test_a_specific_version_can_be_requested(self, service, repo_mock):
        repo_mock.get_plans_by_version.return_value = [_row(version=1, archived_at=_NOW)]
        plans = await service.get_saved(date(2026, 10, 21), date(2026, 10, 21), version=1)
        assert plans[0].version == 1 and plans[0].archived_at is not None
        repo_mock.get_active_plans.assert_not_called()

    async def test_range_must_be_ordered_and_bounded(self, service):
        with pytest.raises(SavedPlanValidationError):
            await service.get_saved(date(2026, 10, 22), date(2026, 10, 21))
        with pytest.raises(SavedPlanValidationError, match="62"):
            await service.get_saved(date(2026, 1, 1), date(2026, 3, 31))

    async def test_history_lists_all_versions(self, service, repo_mock):
        repo_mock.get_history.return_value = [_row(version=2), _row(version=1, archived_at=_NOW)]
        plans = await service.get_history(date(2026, 10, 21))
        assert [(p.version, p.archived_at is None) for p in plans] == [(2, True), (1, False)]

    async def test_items_round_trip_through_the_read_model(self, service, repo_mock):
        repo_mock.get_history.return_value = [_row(items=[{
            "start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:00:00+01:00", "kind": "task",
            "ref_id": 4, "title": "Write", "note": None,
        }])]
        item = (await service.get_history(date(2026, 10, 21)))[0].items[0]
        assert (item.start, item.ref_id, item.title) == ("2026-10-21T09:00:00+01:00", 4, "Write")


class TestMissedBlocks:
    async def test_marking_flags_the_block_with_a_local_timestamp(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(id=3, items=[_block_item(), _block_item()])
        repo_mock.set_block_missed.side_effect = lambda plan, i, at: _row(
            id=plan.id, items=[plan.items[0], {**plan.items[1], "missed": True, "missed_at": at}]
        )

        plan = await service.set_block_missed(3, 1, True)

        _, index, stamp = repo_mock.set_block_missed.call_args.args
        assert index == 1 and stamp is not None and stamp[-6] in "+-"
        assert plan.items[1].missed is True and plan.items[0].missed is None

    async def test_unmarking_clears_the_flag(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(items=[{**_block_item(), "missed": True, "missed_at": "x"}])
        repo_mock.set_block_missed.side_effect = lambda plan, i, at: _row(items=[_block_item()])

        plan = await service.set_block_missed(1, 0, False)

        assert repo_mock.set_block_missed.call_args.args[2] is None
        assert plan.items[0].missed is None

    @pytest.mark.parametrize("index", [-1, 1])
    async def test_block_index_must_exist(self, service, repo_mock, index):
        repo_mock.get_plan.return_value = _row(items=[_block_item()])
        with pytest.raises(SavedPlanNotFoundError, match="no block"):
            await service.set_block_missed(1, index, True)
        repo_mock.set_block_missed.assert_not_called()

    async def test_unknown_plan_is_not_found(self, service, repo_mock):
        repo_mock.get_plan.return_value = None
        with pytest.raises(SavedPlanNotFoundError):
            await service.set_block_missed(9, 0, True)

    async def test_any_kind_can_be_marked(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(items=[{**_block_item(), "kind": "break", "ref_id": None}])
        repo_mock.set_block_missed.side_effect = lambda plan, i, at: _row(items=plan.items)
        await service.set_block_missed(1, 0, True)
        repo_mock.set_block_missed.assert_awaited_once()


class TestMissedByReference:
    @pytest.fixture
    def day(self, repo_mock):
        repo_mock.get_active_plans.return_value = [_row(id=8, items=[
            {**_block_item(), "title": "Training", "ref_id": 4, "start": "2026-10-21T18:00:00+01:00"},
            {**_block_item(), "kind": "transport", "ref_id": None, "title": "Metro to school", "start": "2026-10-21T08:00:00+01:00"},
            {**_block_item(), "title": "Training", "ref_id": 4, "start": "2026-10-21T20:00:00+01:00"},
        ])]
        repo_mock.get_plan.return_value = repo_mock.get_active_plans.return_value[0]
        repo_mock.set_block_missed.side_effect = lambda plan, i, at: plan
        return repo_mock

    async def test_finds_a_free_form_block_by_title(self, service, day):
        await service.set_missed_on(date(2026, 10, 21), True, title="metro")
        assert day.set_block_missed.call_args.args[1] == 1

    async def test_two_matches_need_a_start_time(self, service, day):
        with pytest.raises(SavedPlanValidationError, match="18:00, 20:00"):
            await service.set_missed_on(date(2026, 10, 21), True, ref_id=4)
        await service.set_missed_on(date(2026, 10, 21), True, ref_id=4, start="20:00")
        assert day.set_block_missed.call_args.args[1] == 2

    async def test_ref_id_must_match_the_kind(self, service, day):
        with pytest.raises(SavedPlanNotFoundError):
            await service.set_missed_on(date(2026, 10, 21), True, kind="event", ref_id=4)

    async def test_needs_ref_or_title_and_an_active_plan(self, service, day):
        with pytest.raises(SavedPlanValidationError):
            await service.set_missed_on(date(2026, 10, 21), True)
        day.get_active_plans.return_value = []
        with pytest.raises(SavedPlanNotFoundError, match="No active plan"):
            await service.set_missed_on(date(2026, 10, 21), True, ref_id=4)


def _block_item():
    return {"start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:00:00+01:00", "kind": "task", "ref_id": 4, "title": "Run", "note": None}


class TestManage:
    async def test_archive_marks_the_active_version(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(id=7, version=3)
        repo_mock.archive_plan.side_effect = lambda plan: _row(id=plan.id, version=plan.version, archived_at=_NOW)

        plan = await service.archive(7)

        assert plan.id == 7 and plan.archived_at == _NOW

    async def test_archiving_an_archived_version_is_a_conflict(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(archived_at=_NOW)
        with pytest.raises(SavedPlanConflictError, match="already archived"):
            await service.archive(1)
        repo_mock.archive_plan.assert_not_called()

    async def test_restore_reactivates_an_archived_version(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(id=4, version=1, archived_at=_NOW)
        repo_mock.restore_plan.side_effect = lambda plan: _row(id=plan.id, version=plan.version)

        plan = await service.restore(4)

        assert plan.archived_at is None and plan.version == 1

    async def test_restoring_the_active_version_is_a_conflict(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row()
        with pytest.raises(SavedPlanConflictError, match="already the active"):
            await service.restore(1)
        repo_mock.restore_plan.assert_not_called()

    async def test_a_concurrent_save_during_restore_is_a_conflict(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(archived_at=_NOW)
        repo_mock.restore_plan.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        with pytest.raises(SavedPlanConflictError):
            await service.restore(1)

    async def test_delete_removes_the_version(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(id=9)
        await service.delete(9)
        repo_mock.delete_plan.assert_awaited_once_with(9)

    @pytest.mark.parametrize("action", ["archive", "restore", "delete"])
    async def test_unknown_id_is_not_found(self, service, repo_mock, action):
        repo_mock.get_plan.return_value = None
        with pytest.raises(SavedPlanNotFoundError):
            await getattr(service, action)(99)


def _session(scalar=None, rows=None):
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    result = MagicMock()
    result.scalar.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    session.execute.return_value = result
    return session


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestRepository:
    async def test_saving_archives_the_active_plan_then_inserts_the_next_version(self):
        session = _session(scalar=1)
        repo = DayPlanRepository(session)

        saved = await repo.save_days([(date(2026, 10, 21), [{"title": "x"}], "note")], "mcp")

        archive_sql = _sql(session.execute.call_args_list[0].args[0])
        assert archive_sql.startswith("UPDATE planning.day_plans SET")
        assert "archived_at=now()" in archive_sql
        assert "plan_date = '2026-10-21'" in archive_sql and "archived_at IS NULL" in archive_sql
        assert saved[0].version == 2 and saved[0].source == "mcp" and saved[0].notes == "note"
        session.commit.assert_awaited_once()

    async def test_first_save_of_a_date_is_version_one(self):
        repo = DayPlanRepository(_session(scalar=None))
        saved = await repo.save_days([(date(2026, 10, 21), [], None)], "portal")
        assert saved[0].version == 1

    async def test_every_date_in_the_call_is_archived_and_versioned_separately(self):
        session = _session(scalar=3)
        saved = await DayPlanRepository(session).save_days(
            [(date(2026, 10, 21), [], None), (date(2026, 10, 22), [], None)], "mcp"
        )
        archives = [c for c in session.execute.call_args_list if _sql(c.args[0]).startswith("UPDATE")]
        assert len(archives) == 2
        assert [p.version for p in saved] == [4, 4]
        session.commit.assert_awaited_once()

    async def test_failure_rolls_the_whole_call_back(self):
        session = _session(scalar=None)
        session.flush.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        with pytest.raises(IntegrityError):
            await DayPlanRepository(session).save_days([(date(2026, 10, 21), [], None)], "mcp")
        session.rollback.assert_awaited_once()
        session.commit.assert_not_called()

    async def test_active_range_query(self):
        session = _session()
        await DayPlanRepository(session).get_active_plans(date(2026, 10, 19), date(2026, 10, 25))
        sql = _sql(session.execute.call_args.args[0])
        assert "plan_date >= '2026-10-19'" in sql and "plan_date <= '2026-10-25'" in sql
        assert "archived_at IS NULL" in sql and "ORDER BY planning.day_plans.plan_date" in sql

    async def test_history_is_newest_first(self):
        session = _session()
        await DayPlanRepository(session).get_history(date(2026, 10, 21))
        assert "ORDER BY planning.day_plans.version DESC" in _sql(session.execute.call_args.args[0])

    async def test_marking_a_block_edits_only_that_item_in_place(self):
        session = _session()
        plan = _row(items=[_block_item(), _block_item()])

        await DayPlanRepository(session).set_block_missed(plan, 1, "2026-10-21T21:00:00+01:00")

        assert plan.items[1]["missed"] is True and plan.items[1]["missed_at"] == "2026-10-21T21:00:00+01:00"
        assert "missed" not in plan.items[0]
        session.commit.assert_awaited_once()

    async def test_unmarking_removes_both_keys(self):
        session = _session()
        plan = _row(items=[{**_block_item(), "missed": True, "missed_at": "x"}])
        await DayPlanRepository(session).set_block_missed(plan, 0, None)
        assert "missed" not in plan.items[0] and "missed_at" not in plan.items[0]

    async def test_marking_done_clears_missed_and_the_reverse(self):
        session = _session()
        plan = _row(items=[{**_block_item(), "missed": True, "missed_at": "x"}])
        repo = DayPlanRepository(session)

        await repo.set_block_done(plan, 0, "2026-10-21T21:00:00+01:00")
        assert plan.items[0]["done"] is True and "missed" not in plan.items[0] and "missed_at" not in plan.items[0]

        await repo.set_block_missed(plan, 0, "2026-10-21T22:00:00+01:00")
        assert plan.items[0]["missed"] is True and "done" not in plan.items[0] and "done_at" not in plan.items[0]

    async def test_unmarking_done_leaves_a_missed_flag_alone(self):
        session = _session()
        plan = _row(items=[{**_block_item(), "done": True, "done_at": "x"}])
        await DayPlanRepository(session).set_block_done(plan, 0, None)
        assert "done" not in plan.items[0] and "done_at" not in plan.items[0]

    async def test_get_plan_by_id(self):
        session = _session()
        await DayPlanRepository(session).get_plan(5)
        assert "day_plans.id = 5" in _sql(session.execute.call_args.args[0])

    async def test_archive_commits_the_timestamp(self):
        session = _session()
        plan = _row()
        await DayPlanRepository(session).archive_plan(plan)
        assert plan.archived_at is not None
        session.commit.assert_awaited_once()

    async def test_restore_archives_the_active_plan_before_clearing_this_one(self):
        session = _session()
        plan = _row(plan_date=date(2026, 10, 21), archived_at=_NOW)

        await DayPlanRepository(session).restore_plan(plan)

        sql = _sql(session.execute.call_args.args[0])
        assert sql.startswith("UPDATE planning.day_plans SET") and "archived_at=now()" in sql
        assert "plan_date = '2026-10-21'" in sql and "archived_at IS NULL" in sql
        assert plan.archived_at is None
        session.commit.assert_awaited_once()

    async def test_failed_restore_rolls_back(self):
        session = _session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("duplicate"))
        with pytest.raises(IntegrityError):
            await DayPlanRepository(session).restore_plan(_row(archived_at=_NOW))
        session.rollback.assert_awaited_once()

    async def test_delete_removes_one_row_by_id(self):
        session = _session()
        await DayPlanRepository(session).delete_plan(5)
        assert _sql(session.execute.call_args.args[0]).startswith("DELETE FROM planning.day_plans WHERE planning.day_plans.id = 5")
        session.commit.assert_awaited_once()

    async def test_activity_refs_are_checked_against_the_activities_table(self):
        session = _session(rows=[1])
        assert await DayPlanRepository(session).existing_ref_ids("activity", {1, 2}) == {1}
        assert "organizer.activities.id" in _sql(session.execute.call_args.args[0])

    async def test_no_ids_skips_the_query(self):
        session = _session()
        assert await DayPlanRepository(session).existing_ref_ids("task", set()) == set()
        session.execute.assert_not_called()

    async def test_task_refs_ignore_deleted_tasks(self):
        session = _session(rows=[4])
        found = await DayPlanRepository(session).existing_ref_ids("task", {4, 5})
        assert found == {4}
        assert "tasks.deleted_at IS NULL" in _sql(session.execute.call_args.args[0])


def _edit(*days) -> DayPlansEdit:
    return DayPlansEdit.model_validate({"days": list(days)})


def _edit_day(day="2026-10-21", replace_from="07:50", replace_to="08:40", items=None, notes=None):
    return {"date": day, "replace_from": replace_from, "replace_to": replace_to, "items": items or [], "notes": notes}


def _at(hour, minute=0, day="2026-10-21"):
    return f"{day}T{hour:02d}:{minute:02d}:00+00:00"


class TestEditSchema:
    def test_window_must_be_ordered_hh_mm(self):
        DayPlanEdit(**_edit_day())
        for bad in [("08:40", "07:50"), ("07:50", "07:50"), ("7:50", "08:40"), ("07:50", "24:00")]:
            with pytest.raises(ValidationError):
                DayPlanEdit(**_edit_day(replace_from=bad[0], replace_to=bad[1]))


class TestEdit:
    @pytest.fixture
    def stored(self, repo_mock):
        plan = _row(id=5, version=3, notes="old notes", items=[
            _block(_at(7), _at(7, 30), title="Breakfast"),
            _block(_at(7, 50), _at(8), title="Leave home", missed=True, missed_at="x"),
            _block(_at(8), _at(8, 15), title="Duolingo"),
            _block(_at(8, 40), _at(10, 40), title="PPR form", done=True, done_at="y"),
        ])
        repo_mock.get_active_plans.return_value = [plan]
        return repo_mock

    async def test_blocks_starting_in_the_window_are_replaced_and_the_rest_is_kept_in_order(self, service, stored):
        new = _block(_at(7, 55), _at(8, 45), title="Metro", kind="transport")

        summary = await service.edit(_edit(_edit_day(items=[new])), "mcp")

        entries, source = stored.save_days.call_args.args
        _, items, notes = entries[0]
        assert source == "mcp" and notes == "old notes"
        assert [i["title"] for i in items] == ["Breakfast", "Metro", "PPR form"]
        assert items[2]["done"] is True
        assert summary[0].blocks == 3 and summary[0].version == 2

    async def test_window_end_is_exclusive(self, service, stored):
        await service.edit(_edit(_edit_day(replace_from="08:00", replace_to="08:40")), "mcp")
        titles = [i["title"] for i in stored.save_days.call_args.args[0][0][1]]
        assert "PPR form" in titles and "Duolingo" not in titles

    async def test_empty_items_only_removes(self, service, stored):
        await service.edit(_edit(_edit_day(replace_from="07:00", replace_to="08:00")), "mcp")
        assert [i["title"] for i in stored.save_days.call_args.args[0][0][1]] == ["Duolingo", "PPR form"]

    async def test_notes_are_replaced_when_given(self, service, stored):
        await service.edit(_edit(_edit_day(notes="new notes")), "mcp")
        assert stored.save_days.call_args.args[0][0][2] == "new notes"

    async def test_a_date_without_an_active_plan_is_not_found(self, service, stored):
        with pytest.raises(SavedPlanNotFoundError, match="2026-10-22"):
            await service.edit(_edit(_edit_day(), _edit_day(day="2026-10-22")), "mcp")
        stored.save_days.assert_not_called()

    async def test_repeated_date_is_rejected(self, service, stored):
        with pytest.raises(SavedPlanValidationError, match="repeated"):
            await service.edit(_edit(_edit_day(), _edit_day()), "mcp")

    async def test_new_blocks_are_validated_like_a_save(self, service, stored):
        wrong_day = _block("2026-10-22T09:00:00+00:00", "2026-10-22T10:00:00+00:00", title="Elsewhere")
        with pytest.raises(SavedPlanValidationError, match="starts on 2026-10-22"):
            await service.edit(_edit(_edit_day(items=[wrong_day])), "mcp")
        stored.existing_ref_ids.side_effect = lambda kind, ids: set()
        with pytest.raises(SavedPlanValidationError, match="Unknown task ref_id"):
            await service.edit(_edit(_edit_day(items=[_block(ref_id=99)])), "mcp")
        stored.save_days.assert_not_called()

    async def test_a_concurrent_save_is_a_conflict(self, service, stored):
        stored.save_days.side_effect = IntegrityError("x", {}, Exception())
        with pytest.raises(SavedPlanConflictError):
            await service.edit(_edit(_edit_day()), "mcp")


class TestDoneBlocks:
    async def test_marking_flags_the_block_with_a_local_timestamp(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(id=3, items=[_block_item(), _block_item()])
        repo_mock.set_block_done.side_effect = lambda plan, i, at: _row(
            id=plan.id, items=[plan.items[0], {**plan.items[1], "done": True, "done_at": at}]
        )

        plan = await service.set_block_done(3, 1, True)

        _, index, stamp = repo_mock.set_block_done.call_args.args
        assert index == 1 and stamp[-6] in "+-"
        assert plan.items[1].done is True and plan.items[0].done is None

    async def test_unmarking_passes_none(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(items=[_block_item()])
        repo_mock.set_block_done.side_effect = lambda plan, i, at: plan
        await service.set_block_done(1, 0, False)
        assert repo_mock.set_block_done.call_args.args[2] is None

    async def test_block_index_must_exist(self, service, repo_mock):
        repo_mock.get_plan.return_value = _row(items=[_block_item()])
        with pytest.raises(SavedPlanNotFoundError, match="no block"):
            await service.set_block_done(1, 4, True)

    async def test_done_by_reference_uses_the_same_lookup_as_missed(self, service, repo_mock):
        repo_mock.get_active_plans.return_value = [_row(id=8, items=[{**_block_item(), "title": "Meds", "ref_id": 7}])]
        repo_mock.get_plan.return_value = repo_mock.get_active_plans.return_value[0]
        repo_mock.set_block_done.side_effect = lambda plan, i, at: plan

        await service.set_done_on(date(2026, 10, 21), True, ref_id=7)

        assert repo_mock.set_block_done.call_args.args[1] == 0


class TestReview:
    @freeze_time("2026-10-22 12:00:00")
    async def test_counts_done_missed_unmarked_and_upcoming_per_item(self, service, repo_mock):
        meds = {**_block_item(), "ref_id": 7, "title": "Night meds"}
        repo_mock.get_active_plans.return_value = [
            _row(plan_date=date(2026, 10, 20), items=[
                {**meds, "start": _at(21, 45, "2026-10-20"), "end": _at(22, day="2026-10-20"), "done": True, "done_at": "x"},
                {**_block_item(), "ref_id": 4, "title": "Gym", "start": _at(9, day="2026-10-20"), "end": _at(10, day="2026-10-20"), "missed": True, "missed_at": "x"},
            ]),
            _row(plan_date=date(2026, 10, 21), items=[
                {**meds, "start": _at(21, 45), "end": _at(22)},
                {**_block_item(), "ref_id": 4, "title": "Gym", "start": _at(9), "end": _at(10), "missed": True, "missed_at": "x"},
                {**_block_item(), "kind": "event", "ref_id": 2, "title": "Standup", "start": _at(14), "end": _at(14, 30)},
            ]),
            _row(plan_date=date(2026, 10, 23), items=[
                {**meds, "start": _at(21, 45, "2026-10-23"), "end": _at(22, day="2026-10-23")},
            ]),
        ]

        review = await service.review(date(2026, 10, 20), date(2026, 10, 26))

        by_title = {i.title: i for i in review.items}
        assert "Standup" not in by_title
        assert [i.title for i in review.items] == ["Gym", "Night meds"]
        gym, meds_item = by_title["Gym"], by_title["Night meds"]
        assert (gym.planned, gym.missed, gym.done, gym.missed_dates) == (2, 2, 0, ["2026-10-20", "2026-10-21"])
        assert (meds_item.planned, meds_item.done, meds_item.unmarked, meds_item.upcoming) == (3, 1, 1, 1)
        assert (review.planned, review.done, review.missed, review.unmarked, review.upcoming) == (5, 1, 2, 1, 1)

    async def test_free_form_blocks_group_by_kind_and_title_ignoring_case(self, service, repo_mock):
        repo_mock.get_active_plans.return_value = [
            _row(plan_date=date(2026, 10, 20), items=[{**_block_item(), "kind": "work", "ref_id": None, "title": "Deep work"}]),
            _row(plan_date=date(2026, 10, 21), items=[{**_block_item(), "kind": "work", "ref_id": None, "title": "deep work"}]),
        ]
        review = await service.review(date(2026, 10, 20), date(2026, 10, 21))
        assert len(review.items) == 1 and review.items[0].planned == 2

    async def test_range_is_validated_like_get_saved(self, service):
        with pytest.raises(SavedPlanValidationError):
            await service.review(date(2026, 10, 21), date(2026, 10, 20))
