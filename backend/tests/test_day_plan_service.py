from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from app.features.organizer.calendar_events.schemas import EventRead
from app.features.organizer.routines.schemas import RoutineRead, RoutineStepRead
from app.features.organizer.tasks.schemas import TaskRead
from app.features.planning.schemas import PlanningSettingsRead
from app.features.planning.service import DayPlanService

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _settings(**kw) -> PlanningSettingsRead:
    defaults = dict(work_target_minutes=480, preferred_work_windows=[], work_tag="work", office_tag="office")
    defaults.update(kw)
    return PlanningSettingsRead(**defaults)


def _event(id, title, start, end, **kw) -> EventRead:
    return EventRead(id=id, title=title, start_datetime=start, end_datetime=end, **kw)


def _step(id, title, **kw) -> RoutineStepRead:
    defaults = dict(id=id, routine_id=1, position=id, title=title, created_at=_NOW, updated_at=_NOW)
    defaults.update(kw)
    return RoutineStepRead(**defaults)


def _routine(id=1, name="Routine", steps=None, **kw) -> RoutineRead:
    return RoutineRead(id=id, name=name, steps=steps or [], created_at=_NOW, updated_at=_NOW, **kw)


def _task(id, title="Task", **kw) -> TaskRead:
    defaults = dict(id=id, title=title, created_at=datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc))
    defaults.update(kw)
    return TaskRead(**defaults)


@pytest.fixture
def parts():
    events = AsyncMock()
    events.get_events.return_value = []
    routines = AsyncMock()
    routines.get_routines_by_ids.return_value = []
    routines.get_active_scheduled_routines.return_value = []
    routines.get_note_titles.return_value = {}
    tasks = AsyncMock()
    tasks.get_tasks.return_value = []
    study = AsyncMock()
    study.get_overview.return_value = SimpleNamespace(active=[], backlog=[], max_active_plans=2)
    language = AsyncMock()
    language.get_daily_progress.return_value = []
    shopping = AsyncMock()
    shopping.list_items.return_value = []
    shopping.list_due_recurrences.return_value = []
    settings = AsyncMock()
    settings.get.return_value = _settings()
    saved = AsyncMock()
    saved.get_saved.return_value = []
    return SimpleNamespace(
        events=events, routines=routines, tasks=tasks, study=study, language=language, shopping=shopping,
        settings=settings, saved=saved,
    )


@pytest.fixture
def service(parts):
    return DayPlanService(
        event_service=parts.events, routine_service=parts.routines, task_service=parts.tasks,
        study_service=parts.study, language_service=parts.language, shopping_service=parts.shopping,
        settings_service=parts.settings, saved_plan_service=parts.saved,
    )


def _dump(plan) -> dict:
    return plan.model_dump(mode="json", exclude_none=True)


@freeze_time("2026-10-21 08:00:00")  # 09:00 in Lisbon
class TestSingleDay:
    async def test_basic_shape(self, service):
        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert plan["date"] == "2026-10-21"
        assert plan["timezone"] == "Europe/Lisbon"
        assert plan["timeline"] == [] and plan["routine_blocks"] == [] and plan["all_day"] == []
        assert "days" not in plan
        assert plan["work"] == {"target_minutes": 480, "committed_minutes": 0, "remaining_minutes": 480}
        assert plan["preferences"] == {"work_target_minutes": 480}
        assert "shopping" not in plan and "office" not in plan and "saved_plan" not in plan

    async def test_defaults_to_today_in_the_local_zone(self, service):
        plan = await service.get_plan()
        assert plan.date == "2026-10-21"

    async def test_requests_events_for_exactly_the_requested_window(self, service, parts):
        await service.get_plan(date(2026, 10, 21), days=3)
        filters = parts.events.get_events.call_args_list[0].args[0]
        assert filters.start_from == datetime(2026, 10, 21, 0, 0)
        assert filters.start_to == datetime(2026, 10, 23, 23, 59, 59)

    async def test_timeline_work_and_all_day(self, service, parts):
        parts.events.get_events.return_value = [
            _event(1, "Standup", datetime(2026, 10, 21, 10, 0), datetime(2026, 10, 21, 10, 30), tags=["work"]),
            _event(2, "Call", datetime(2026, 10, 21, 14, 0), datetime(2026, 10, 21, 15, 0), tags=["work"]),
            _event(3, "Card due", datetime(2026, 10, 21, 0, 0), datetime(2026, 10, 21, 23, 59, 59), all_day=True),
        ]
        parts.settings.get.return_value = _settings(preferred_work_windows=["10:00-14:00"])

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert [i["title"] for i in plan["timeline"]] == ["Standup", "Call"]
        assert plan["all_day"] == [{"title": "Card due", "event_id": 3}]
        assert plan["work"] == {
            "target_minutes": 480, "committed_minutes": 90, "remaining_minutes": 390,
            "preferred_windows": ["10:00-14:00"],
        }

    async def test_work_minutes_argument_overrides_the_target(self, service):
        plan = _dump(await service.get_plan(date(2026, 10, 21), work_minutes=0))
        assert plan["work"]["target_minutes"] == 0 and plan["work"]["remaining_minutes"] == 0

    async def test_event_routine_expands_around_the_event(self, service, parts):
        parts.events.get_events.return_value = [
            _event(7, "Class", datetime(2026, 10, 21, 20, 0), datetime(2026, 10, 21, 21, 0), routine_id=1, travel_minutes=25),
        ]
        parts.routines.get_routines_by_ids.return_value = [
            _routine(1, "Dinner", steps=[_step(101, "Prepare", anchor="start", offset_minutes=-120, duration_minutes=40, checklist_note_id=26)])
        ]
        parts.routines.get_note_titles.return_value = {26: "Dinner checklist"}

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert [(i["kind"], i["start"][11:16]) for i in plan["timeline"]] == [
            ("routine_step", "18:00"), ("travel", "19:35"), ("event", "20:00"), ("travel", "21:00"),
        ]
        assert plan["timeline"][0]["checklist_note_title"] == "Dinner checklist"
        parts.routines.get_routines_by_ids.assert_awaited_once_with([1])

    async def test_scheduled_routine_appears_without_any_event(self, service, parts):
        parts.routines.get_active_scheduled_routines.return_value = [
            _routine(
                2, "Morning", recurrence_rule="FREQ=DAILY", starts_on=date(2026, 10, 1),
                steps=[
                    _step(110, "Shower", duration_minutes=15, window_start=time(7, 30), window_end=time(9, 0), context="home"),
                    _step(120, "Lunch", duration_minutes=45, window_start=time(13, 0), window_end=time(13, 45)),
                ],
            )
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert plan["timeline"] == []
        assert plan["routine_blocks"] == [
            {"routine": "Morning", "routine_step_id": 110, "title": "Shower", "duration_minutes": 15,
             "window": "07:30-09:00", "context": "home"},
            {"routine": "Morning", "routine_step_id": 120, "title": "Lunch", "duration_minutes": 45,
             "window": "13:00-13:45", "fixed": True},
        ]

    async def test_scheduled_routine_skips_days_its_rule_excludes(self, service, parts):
        parts.routines.get_active_scheduled_routines.return_value = [
            _routine(2, "Mondays", recurrence_rule="FREQ=WEEKLY;BYDAY=MO", starts_on=date(2026, 10, 1),
                     steps=[_step(1, "Plan week", window_start=time(9), window_end=time(10), duration_minutes=30)])
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))  # a Wednesday
        assert plan["routine_blocks"] == []

    async def test_invalid_stored_rule_becomes_a_warning_not_a_crash(self, service, parts):
        parts.routines.get_active_scheduled_routines.return_value = [
            _routine(2, "Broken", recurrence_rule="FREQ=SOMETIMES", starts_on=date(2026, 10, 1))
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert any("Broken" in w and "invalid recurrence rule" in w for w in plan["warnings"])

    async def test_overlaps_are_reported_in_warnings(self, service, parts):
        parts.events.get_events.return_value = [
            _event(1, "A", datetime(2026, 10, 21, 10, 0), datetime(2026, 10, 21, 11, 0)),
            _event(2, "B", datetime(2026, 10, 21, 10, 30), datetime(2026, 10, 21, 11, 30)),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert any("overlaps" in w for w in plan["warnings"])


@freeze_time("2026-10-21 08:00:00")
class TestMultiDay:
    async def test_three_days_return_three_timelines(self, service, parts):
        parts.events.get_events.return_value = [
            _event(1, "Mon", datetime(2026, 10, 21, 10, 0), datetime(2026, 10, 21, 11, 0)),
            _event(2, "Thu", datetime(2026, 10, 22, 10, 0), datetime(2026, 10, 22, 11, 0)),
            _event(3, "Fri", datetime(2026, 10, 23, 10, 0), datetime(2026, 10, 23, 11, 0)),
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21), days=3))

        assert "timeline" not in plan and "work" not in plan
        assert [d["date"] for d in plan["days"]] == ["2026-10-21", "2026-10-22", "2026-10-23"]
        assert [[i["title"] for i in d["timeline"]] for d in plan["days"]] == [["Mon"], ["Thu"], ["Fri"]]
        assert all("work" in d for d in plan["days"])

    async def test_daily_recurring_task_appears_once_with_three_due_dates(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(240, "Guitar practice", recurrence_rule="FREQ=DAILY", estimate_minutes=10, context="home", tags=["music"]),
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21), days=3))

        assert len(plan["recurring_tasks"]) == 1
        assert plan["recurring_tasks"][0]["due_dates"] == ["2026-10-21", "2026-10-22", "2026-10-23"]
        assert plan["recurring_tasks"][0]["tags"] == ["music"]


@freeze_time("2026-10-25 12:00:00")
class TestDstDay:
    async def test_25_hour_day_computes_correct_work_durations(self, service, parts):
        parts.events.get_events.return_value = [
            _event(1, "Night shift", datetime(2026, 10, 25, 0, 0), datetime(2026, 10, 25, 3, 0), tags=["work"]),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 25)))
        assert plan["work"]["committed_minutes"] == 240
        assert plan["timeline"][0]["start"] == "2026-10-25T00:00:00+01:00"
        assert plan["timeline"][0]["end"] == "2026-10-25T03:00:00+00:00"


@freeze_time("2026-10-21 08:00:00")  # Wednesday 09:00 Lisbon
class TestTaskSections:
    async def test_tasks_are_partitioned(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(1, "Overdue", deadline=datetime(2026, 10, 20, 18, 0), urgency="URGENT", priority="HIGH"),
            _task(2, "Due soon", deadline=datetime(2026, 10, 23, 23, 59)),
            _task(3, "Due today later", deadline=datetime(2026, 10, 21, 18, 0)),
            _task(4, "Due today but past", deadline=datetime(2026, 10, 21, 8, 0)),
            _task(5, "Far future", deadline=datetime(2026, 12, 1, 10, 0)),
            _task(6, "Backlog", priority="LOW", tags=["home"]),
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert [t["id"] for t in plan["overdue_tasks"]] == [1, 4]
        assert [t["id"] for t in plan["due_tasks"]] == [3, 2]
        assert [t["id"] for t in plan["backlog_tasks"]] == [6]
        assert plan["overdue_tasks"][0]["deadline"] == "2026-10-20T18:00:00+01:00"
        assert plan["overdue_tasks"][0]["urgency"] == "URGENT"
        assert plan["backlog_tasks"][0]["tags"] == ["home"]
        assert plan["backlog_tasks"][0]["created_at"] == "2026-10-10T10:00:00+01:00"

    async def test_future_week_plan_treats_pre_range_deadlines_as_overdue(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(1, "Due before the week", deadline=datetime(2026, 10, 27, 12, 0)),
            _task(2, "Due in the week", deadline=datetime(2026, 11, 3, 12, 0)),
        ]
        plan = _dump(await service.get_plan(date(2026, 11, 2), days=7))
        assert [t["id"] for t in plan["overdue_tasks"]] == [1]
        assert [t["id"] for t in plan["due_tasks"]] == [2]

    async def test_task_available_after_the_range_is_left_out(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(1, "Weekend job", available_from=datetime(2026, 10, 24, 0, 0)),
            _task(2, "Available soon", available_from=datetime(2026, 10, 21, 15, 0)),
        ]
        today_only = _dump(await service.get_plan(date(2026, 10, 21)))
        assert [t["id"] for t in today_only["backlog_tasks"]] == [2]
        assert today_only["backlog_tasks"][0]["available_from"] == "2026-10-21T15:00:00+01:00"

        week = _dump(await service.get_plan(date(2026, 10, 21), days=7))
        assert [t["id"] for t in week["backlog_tasks"]] == [1, 2]

    async def test_backlog_is_capped_in_repository_order(self, service, parts):
        parts.tasks.get_tasks.return_value = [_task(i) for i in range(1, 41)]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert [t["id"] for t in plan["backlog_tasks"]] == list(range(1, 31))

    async def test_weekly_byday_task_only_on_its_days(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(9, "Trash", recurrence_rule="FREQ=WEEKLY;BYDAY=WE,SA"),
            _task(10, "Mondays only", recurrence_rule="FREQ=WEEKLY;BYDAY=MO"),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21), days=7))
        assert [(t["id"], t["due_dates"]) for t in plan["recurring_tasks"]] == [(9, ["2026-10-21", "2026-10-24"]), (10, ["2026-10-26"])]

    async def test_recurring_task_already_done_today_drops_today(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(9, "Daily habit", recurrence_rule="FREQ=DAILY", is_done_in_cycle=True),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21), days=2))
        assert plan["recurring_tasks"][0]["due_dates"] == ["2026-10-22"]

    async def test_recurring_task_with_nothing_left_is_omitted(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(9, "Daily habit", recurrence_rule="FREQ=DAILY", is_done_in_cycle=True),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert plan["recurring_tasks"] == []

    async def test_flexible_cadence_tasks_are_flagged_instead_of_dated(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(11, "Monthly review", recurrence_rule="FREQ=MONTHLY"),
            _task(12, "Done this month", recurrence_rule="FREQ=MONTHLY", is_done_in_cycle=True),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21), days=3))
        assert [(t["id"], t["flexible"]) for t in plan["recurring_tasks"]] == [(11, True)]
        assert "due_dates" not in plan["recurring_tasks"][0]

    async def test_missing_estimate_and_context_produce_grouped_warnings(self, service, parts):
        parts.tasks.get_tasks.return_value = [
            _task(1, "Nothing known", deadline=datetime(2026, 10, 22, 10, 0)),
            _task(2, "Has estimate", estimate_minutes=10),
            _task(3, "Has context", context="home"),
            _task(4, "Complete", estimate_minutes=10, context="phone"),
        ]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert plan["warnings"] == [
            "Task 1 has no estimate and no context; assumed 30 min / anywhere.",
            "Task 3 has no estimate; assumed 30 min.",
            "Task 2 has no context; assumed anywhere.",
        ]

    async def test_assumed_values_are_never_stored_or_shown_as_data(self, service, parts):
        parts.tasks.get_tasks.return_value = [_task(1)]
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert "estimate_minutes" not in plan["backlog_tasks"][0]
        assert "context" not in plan["backlog_tasks"][0]


@freeze_time("2026-10-21 08:00:00")
class TestOtherSections:
    async def test_office_section_off_by_default(self, service, parts):
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert "office" not in plan
        assert parts.events.get_events.await_count == 1

    async def test_office_section_counts_the_week(self, service, parts):
        parts.settings.get.return_value = _settings(office_days_per_week=4, office_min_minutes=60)
        parts.events.get_events.side_effect = [
            [],
            [
                _event(1, "Office", datetime(2026, 10, 19, 9, 0), datetime(2026, 10, 19, 17, 0), tags=["office"]),
                _event(2, "Short", datetime(2026, 10, 20, 9, 0), datetime(2026, 10, 20, 9, 20), tags=["office"]),
            ],
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert plan["office"] == {"goal_per_week": 4, "min_minutes": 60, "planned_this_week": 1, "days_left_in_week": 5}
        office_filters = parts.events.get_events.call_args_list[1].args[0]
        assert office_filters.tags == ["office"]
        assert office_filters.start_from == datetime(2026, 10, 19, 0, 0)
        assert office_filters.start_to == datetime(2026, 10, 25, 23, 59, 59)

    async def test_study_section_caps_items_and_skips_done_ones(self, service, parts):
        items = [SimpleNamespace(id=i, description=f"Item {i}", is_done=(i == 1)) for i in range(1, 9)]
        plan_orm = SimpleNamespace(id=3, title="Graphs", goal="Pass", priority="high", tags=["algo"], items=items)
        empty = SimpleNamespace(id=4, title="Done", goal="x", priority="low", tags=[], items=[SimpleNamespace(id=9, description="d", is_done=True)])
        parts.study.get_overview.return_value = SimpleNamespace(active=[plan_orm, empty], backlog=[], max_active_plans=2)
        parts.language.get_daily_progress.return_value = [
            SimpleNamespace(track_code="es", daily_quota=20, completed_today=8, quota_met=False),
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21)))

        assert len(plan["study"]["plans"]) == 1
        summary = plan["study"]["plans"][0]
        assert (summary["plan_id"], summary["goal"], summary["tags"]) == (3, "Pass", ["algo"])
        assert [i["item_id"] for i in summary["open_items"]] == [2, 3, 4, 5, 6]
        assert plan["study"]["language"] == [{"track": "es", "daily_quota": 20, "done_today": 8, "quota_met": False}]

    async def test_shopping_section_summarises_pending_and_due(self, service, parts):
        parts.shopping.list_items.return_value = [object()] * 12
        parts.shopping.list_due_recurrences.return_value = [object()] * 3
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert plan["shopping"] == {
            "pending_items": 12, "due_recurring": 3, "suggested_run": {"estimate_minutes": 45, "context": "out"},
        }

    async def test_shopping_section_omitted_when_nothing_to_buy(self, service):
        assert "shopping" not in _dump(await service.get_plan(date(2026, 10, 21)))

    async def test_preferences_only_include_what_is_set(self, service, parts):
        parts.settings.get.return_value = _settings(wake_time="07:30", sleep_time="23:30", preferred_work_windows=["10:00-14:00"])
        plan = _dump(await service.get_plan(date(2026, 10, 21)))
        assert plan["preferences"] == {
            "wake_time": "07:30", "sleep_time": "23:30", "work_target_minutes": 480,
            "preferred_work_windows": ["10:00-14:00"],
        }


@freeze_time("2026-10-21 08:00:00")
class TestSavedPlanSection:
    async def test_saved_plan_is_included_for_the_requested_dates(self, service, parts):
        from app.features.planning.saved_plans.schemas import SavedDayPlanRead

        parts.saved.get_saved.return_value = [
            SavedDayPlanRead(
                id=5, plan_date=date(2026, 10, 21), version=2, notes="Light day", source="mcp",
                created_at=_NOW, updated_at=_NOW,
                items=[{"start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:00:00+01:00", "kind": "task",
                        "ref_id": 4, "title": "Write", "note": None}],
            )
        ]

        plan = _dump(await service.get_plan(date(2026, 10, 21), days=3))

        parts.saved.get_saved.assert_awaited_once_with(date(2026, 10, 21), date(2026, 10, 23))
        assert plan["saved_plan"] == [{
            "plan_date": "2026-10-21", "version": 2, "notes": "Light day",
            "items": [{"start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:00:00+01:00", "kind": "task",
                       "ref_id": 4, "title": "Write"}],
        }]

    async def test_no_saved_plan_means_the_section_is_omitted(self, service):
        assert "saved_plan" not in _dump(await service.get_plan(date(2026, 10, 21)))
