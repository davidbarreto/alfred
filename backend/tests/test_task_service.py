import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from app.features.organizer.tasks.service import TaskService, _compute_streak, _missed_count
from app.features.organizer.tasks.recurrence import (
    compute_streak,
    is_done_in_cycle,
    is_due_today,
    missed_count,
    parse_byday as _parse_byday,
)
from app.features.organizer.tasks.schemas import TaskCompletionRead, TaskCreate, TaskUpdate, TaskFilters, TaskRead


def _make_task_read(**kwargs):
    defaults = dict(
        id=1, title="Test Task", status="TODO",
        priority="LOW", urgency="NORMAL", tags=[],
        deadline=None, recurrence_rule=None, is_done_today=False,
    )
    defaults.update(kwargs)
    return TaskRead(**defaults)


def _make_task_orm(**kwargs):
    task = MagicMock()
    task.id = kwargs.get("id", 1)
    task.title = kwargs.get("title", "Test Task")
    task.status = kwargs.get("status", "TODO")
    task.priority = kwargs.get("priority", "LOW")
    task.urgency = kwargs.get("urgency", "NORMAL")
    task.deadline = kwargs.get("deadline", None)
    task.recurrence_rule = kwargs.get("recurrence_rule", None)
    task.tags = kwargs.get("tags", [])
    task.provider_id = kwargs.get("provider_id", "provider-1")
    return task


@pytest.fixture
def mock_provider():
    return AsyncMock()


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_embedding_service():
    svc = AsyncMock()
    svc.embed = AsyncMock()
    svc.embed_background = MagicMock()
    svc.delete_by_source = AsyncMock()
    return svc


@pytest.fixture
def service(mock_provider, mock_session):
    svc = TaskService(provider=mock_provider, session=mock_session)
    svc._repo = AsyncMock()
    return svc


@pytest.fixture
def service_with_embeddings(mock_provider, mock_session, mock_embedding_service):
    svc = TaskService(provider=mock_provider, session=mock_session, embedding_service=mock_embedding_service)
    svc._repo = AsyncMock()
    return svc


class TestGetTask:
    async def test_returns_task_read_when_found(self, service):
        task_orm = _make_task_orm()
        service._repo.get_task.return_value = task_orm

        result = await service.get_task(1)

        service._repo.get_task.assert_called_once_with(1)
        assert result is not None
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_task.return_value = None

        result = await service.get_task(999)
        assert result is None

    async def test_returns_task_read_type(self, service):
        service._repo.get_task.return_value = _make_task_orm()
        result = await service.get_task(1)
        assert isinstance(result, TaskRead)

    async def test_computes_is_done_in_cycle_for_recurring(self, service):
        today = date.today()
        task_orm = _make_task_orm(recurrence_rule="FREQ=MONTHLY")
        service._repo.get_task.return_value = task_orm
        service._repo.get_completed_task_ids_for_date.return_value = set()
        service._repo.get_completions_by_task.return_value = {1: [today.replace(day=1)]}

        result = await service.get_task(1)

        assert result.is_done_in_cycle is True


class TestGetTasks:
    async def test_returns_list_of_task_reads(self, service):
        service._repo.get_tasks.return_value = [_make_task_orm(id=i) for i in range(3)]

        result = await service.get_tasks(TaskFilters())

        assert len(result) == 3
        assert all(isinstance(t, TaskRead) for t in result)

    async def test_empty_list(self, service):
        service._repo.get_tasks.return_value = []
        result = await service.get_tasks(TaskFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.get_tasks.return_value = []
        filters = TaskFilters(status="TODO", priority="HIGH")
        await service.get_tasks(filters)
        service._repo.get_tasks.assert_called_once_with(filters)

    async def test_computes_is_done_in_cycle_for_recurring(self, service):
        today = date.today()
        task_orm = _make_task_orm(id=1, recurrence_rule="FREQ=MONTHLY")
        service._repo.get_tasks.return_value = [task_orm]
        service._repo.get_completed_task_ids_for_date.return_value = set()
        service._repo.get_completions_by_task.return_value = {1: [today.replace(day=1)]}

        result = await service.get_tasks(TaskFilters())

        assert result[0].is_done_in_cycle is True

    async def test_due_today_excludes_dated_task_not_due_today(self, service):
        tomorrow = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
        service._repo.get_tasks.return_value = [_make_task_orm(id=1, deadline=tomorrow)]

        result = await service.get_tasks(TaskFilters(due_today=True))

        assert result == []

    async def test_due_today_includes_undated_non_recurring_task(self, service):
        service._repo.get_tasks.return_value = [_make_task_orm(id=1, deadline=None, recurrence_rule=None)]

        result = await service.get_tasks(TaskFilters(due_today=True))

        assert len(result) == 1

    async def test_due_today_excludes_recurring_task_not_scheduled_today(self, service):
        # Pick whatever weekday isn't today so the rule never matches.
        other_day = "MO" if date.today().weekday() != 0 else "TU"
        task_orm = _make_task_orm(id=1, recurrence_rule=f"FREQ=WEEKLY;BYDAY={other_day}")
        service._repo.get_tasks.return_value = [task_orm]
        service._repo.get_completed_task_ids_for_date.return_value = set()
        service._repo.get_completions_by_task.return_value = {1: []}

        result = await service.get_tasks(TaskFilters(due_today=True))

        assert result == []

    async def test_due_today_includes_recurring_task_scheduled_today(self, service):
        today_code = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][date.today().weekday()]
        task_orm = _make_task_orm(id=1, recurrence_rule=f"FREQ=WEEKLY;BYDAY={today_code}")
        service._repo.get_tasks.return_value = [task_orm]
        service._repo.get_completed_task_ids_for_date.return_value = set()
        service._repo.get_completions_by_task.return_value = {1: []}

        result = await service.get_tasks(TaskFilters(due_today=True))

        assert len(result) == 1


class TestCreateTask:
    async def test_calls_provider_create(self, service, mock_provider):
        task_create = TaskCreate(title="New Task")
        mock_provider.create.return_value = {"id": "provider-abc"}
        service._repo.create_task.return_value = _make_task_orm(title="New Task")

        await service.create_task(task_create)

        mock_provider.create.assert_called_once()

    async def test_calls_repo_create_with_provider_id(self, service, mock_provider):
        task_create = TaskCreate(title="New Task")
        mock_provider.create.return_value = {"id": "provider-xyz"}
        service._repo.create_task.return_value = _make_task_orm()

        await service.create_task(task_create)

        service._repo.create_task.assert_called_once_with(task_create, "provider-xyz")

    async def test_returns_task_read(self, service, mock_provider):
        mock_provider.create.return_value = {"id": "provider-1"}
        service._repo.create_task.return_value = _make_task_orm()

        result = await service.create_task(TaskCreate(title="Test"))
        assert isinstance(result, TaskRead)


class TestUpdateTask:
    async def test_returns_updated_task(self, service):
        service._repo.update_task.return_value = _make_task_orm(status="DONE")
        task_update = TaskUpdate(status="DONE")

        result = await service.update_task(1, task_update)

        service._repo.update_task.assert_called_once_with(1, task_update)
        assert isinstance(result, TaskRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_task.return_value = None
        result = await service.update_task(999, TaskUpdate(status="DONE"))
        assert result is None


class TestDeleteTask:
    async def test_calls_delete_when_found(self, service):
        service._repo.get_task.return_value = _make_task_orm()

        await service.delete_task(1)

        service._repo.delete_task.assert_called_once_with(1)

    async def test_does_not_call_delete_when_not_found(self, service):
        service._repo.get_task.return_value = None

        await service.delete_task(999)

        service._repo.delete_task.assert_not_called()


class TestTaskEmbedding:
    async def test_embed_called_on_create(self, service_with_embeddings, mock_provider, mock_embedding_service):
        mock_provider.create.return_value = {"id": "provider-1"}
        service_with_embeddings._repo.create_task.return_value = _make_task_orm(id=7, title="Buy milk")

        await service_with_embeddings.create_task(TaskCreate(title="Buy milk"))

        mock_embedding_service.embed_background.assert_called_once()
        call_arg = mock_embedding_service.embed_background.call_args[0][0]
        assert call_arg.source_type == "task"
        assert call_arg.source_id == 7
        assert call_arg.content == "Buy milk"

    async def test_embed_not_called_without_embedding_service(self, service, mock_provider):
        mock_provider.create.return_value = {"id": "provider-1"}
        service._repo.create_task.return_value = _make_task_orm()

        await service.create_task(TaskCreate(title="Test"))

        assert service._embedding_service is None

    async def test_embed_called_on_title_update(self, service_with_embeddings, mock_embedding_service):
        service_with_embeddings._repo.get_task.return_value = _make_task_orm()
        service_with_embeddings._repo.update_task.return_value = _make_task_orm(title="New title")

        await service_with_embeddings.update_task(1, TaskUpdate(title="New title"))

        mock_embedding_service.embed_background.assert_called_once()

    async def test_embed_not_called_on_non_title_update(self, service_with_embeddings, mock_embedding_service):
        service_with_embeddings._repo.get_task.return_value = _make_task_orm()
        service_with_embeddings._repo.update_task.return_value = _make_task_orm(status="DONE")

        await service_with_embeddings.update_task(1, TaskUpdate(status="DONE"))

        mock_embedding_service.embed_background.assert_not_called()

    async def test_delete_by_source_called_on_delete(self, service_with_embeddings, mock_provider, mock_embedding_service):
        service_with_embeddings._repo.get_task.return_value = _make_task_orm(id=4)

        await service_with_embeddings.delete_task(4)

        mock_embedding_service.delete_by_source.assert_called_once_with("task", 4)

    async def test_create_does_not_use_the_blocking_embed_call(self, service_with_embeddings, mock_provider, mock_embedding_service):
        mock_provider.create.return_value = {"id": "provider-1"}
        service_with_embeddings._repo.create_task.return_value = _make_task_orm()

        result = await service_with_embeddings.create_task(TaskCreate(title="Test"))

        assert isinstance(result, TaskRead)
        mock_embedding_service.embed.assert_not_called()


class TestCompleteTask:
    async def test_non_recurring_sets_status_done(self, service):
        task_orm = _make_task_orm(recurrence_rule=None)
        service._repo.get_task.return_value = task_orm
        service._repo.complete_task.return_value = _make_task_orm(status="DONE")

        result = await service.complete_task(1)

        service._repo.complete_task.assert_called_once_with(1)
        assert isinstance(result, TaskRead)
        assert result.status == "DONE"

    async def test_recurring_inserts_completion_row(self, service):
        task_orm = _make_task_orm(recurrence_rule="FREQ=DAILY")
        service._repo.get_task.return_value = task_orm
        service._repo.get_completion.return_value = None

        completion = MagicMock()
        completion.id = 10
        completion.task_id = 1
        completion.occurrence_date = date(2026, 6, 22)
        completion.completed_at = MagicMock()
        service._repo.complete_occurrence.return_value = completion

        result = await service.complete_task(1, date(2026, 6, 22))

        service._repo.complete_occurrence.assert_called_once_with(1, date(2026, 6, 22))
        assert isinstance(result, TaskCompletionRead)

    async def test_recurring_defaults_to_today(self, service):
        task_orm = _make_task_orm(recurrence_rule="FREQ=WEEKLY")
        service._repo.get_task.return_value = task_orm
        service._repo.get_completion.return_value = None
        service._repo.complete_occurrence.return_value = MagicMock(
            id=1, task_id=1, occurrence_date=date.today(), completed_at=MagicMock()
        )

        await service.complete_task(1)

        service._repo.complete_occurrence.assert_called_once_with(1, date.today())

    async def test_recurring_idempotent_when_already_done(self, service):
        task_orm = _make_task_orm(recurrence_rule="FREQ=DAILY")
        service._repo.get_task.return_value = task_orm
        existing = MagicMock(id=5, task_id=1, occurrence_date=date(2026, 6, 22), completed_at=MagicMock())
        service._repo.get_completion.return_value = existing

        result = await service.complete_task(1, date(2026, 6, 22))

        service._repo.complete_occurrence.assert_not_called()
        assert isinstance(result, TaskCompletionRead)

    async def test_returns_none_when_task_not_found(self, service):
        service._repo.get_task.return_value = None
        result = await service.complete_task(999)
        assert result is None


class TestCancelTask:
    async def test_cancels_recurring_task(self, service):
        task_orm = _make_task_orm(status="TODO", recurrence_rule="FREQ=DAILY")
        service._repo.get_task.return_value = task_orm
        service._repo.update_task.return_value = _make_task_orm(status="CANCELLED", recurrence_rule="FREQ=DAILY")

        result = await service.cancel_task(1)

        service._repo.update_task.assert_called_once_with(1, TaskUpdate(status="CANCELLED"))
        assert isinstance(result, TaskRead)

    async def test_rejects_non_recurring(self, service):
        service._repo.get_task.return_value = _make_task_orm(recurrence_rule=None)

        with pytest.raises(ValueError, match="not recurring"):
            await service.cancel_task(1)

    async def test_rejects_already_terminal(self, service):
        service._repo.get_task.return_value = _make_task_orm(status="DONE", recurrence_rule="FREQ=DAILY")

        with pytest.raises(ValueError, match="terminal"):
            await service.cancel_task(1)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_task.return_value = None
        result = await service.cancel_task(999)
        assert result is None


class TestComputeStreak:
    def test_empty_dates_returns_zero(self):
        assert _compute_streak([], "FREQ=DAILY", date.today()) == 0

    # --- DAILY ---

    def test_daily_single_today(self):
        today = date(2025, 6, 10)
        assert _compute_streak([today], "FREQ=DAILY", today) == 1

    def test_daily_consecutive_days(self):
        today = date(2025, 6, 10)
        dates = [today - timedelta(days=i) for i in range(5)]
        assert _compute_streak(dates, "FREQ=DAILY", today) == 5

    def test_daily_streak_counts_if_not_yet_done_today(self):
        today = date(2025, 6, 10)
        yesterday = today - timedelta(days=1)
        dates = [yesterday - timedelta(days=i) for i in range(3)]
        assert _compute_streak(dates, "FREQ=DAILY", today) == 3

    def test_daily_streak_broken_if_gap(self):
        today = date(2025, 6, 10)
        dates = [today, today - timedelta(days=2)]  # missed yesterday
        assert _compute_streak(dates, "FREQ=DAILY", today) == 1

    def test_daily_streak_zero_if_last_completion_too_old(self):
        today = date(2025, 6, 10)
        assert _compute_streak([today - timedelta(days=2)], "FREQ=DAILY", today) == 0

    def test_daily_deduplicates_same_date(self):
        today = date(2025, 6, 10)
        dates = [today, today, today - timedelta(days=1)]
        assert _compute_streak(dates, "FREQ=DAILY", today) == 2

    # --- WEEKLY ---

    def test_weekly_single_this_week(self):
        today = date(2025, 6, 10)  # Tuesday
        assert _compute_streak([today], "FREQ=WEEKLY", today) == 1

    def test_weekly_consecutive_weeks(self):
        today = date(2025, 6, 10)
        dates = [today - timedelta(weeks=i) for i in range(4)]
        assert _compute_streak(dates, "FREQ=WEEKLY", today) == 4

    def test_weekly_streak_zero_if_skipped_week(self):
        today = date(2025, 6, 10)
        dates = [today, today - timedelta(weeks=2)]  # skipped a week
        assert _compute_streak(dates, "FREQ=WEEKLY", today) == 1

    def test_weekly_streak_zero_if_too_old(self):
        today = date(2025, 6, 10)
        assert _compute_streak([today - timedelta(weeks=2)], "FREQ=WEEKLY", today) == 0

    # --- MONTHLY ---

    def test_monthly_single_this_month(self):
        today = date(2025, 6, 10)
        assert _compute_streak([today], "FREQ=MONTHLY", today) == 1

    def test_monthly_consecutive_months(self):
        today = date(2025, 6, 10)
        dates = [date(2025, 6, 5), date(2025, 5, 3), date(2025, 4, 20), date(2025, 3, 1)]
        assert _compute_streak(dates, "FREQ=MONTHLY", today) == 4

    def test_monthly_streak_zero_if_skipped_month(self):
        today = date(2025, 6, 10)
        dates = [date(2025, 6, 5), date(2025, 4, 3)]  # skipped May
        assert _compute_streak(dates, "FREQ=MONTHLY", today) == 1

    def test_monthly_streak_zero_if_too_old(self):
        today = date(2025, 6, 10)
        assert _compute_streak([date(2025, 4, 1)], "FREQ=MONTHLY", today) == 0

    # --- YEARLY / fallback ---

    def test_yearly_returns_total_count(self):
        today = date(2025, 6, 10)
        dates = [date(2025, 1, 1), date(2024, 1, 1), date(2023, 1, 1)]
        assert _compute_streak(dates, "FREQ=YEARLY", today) == 3

    def test_unknown_rule_returns_total_count(self):
        today = date(2025, 6, 10)
        dates = [date(2025, 1, 1), date(2024, 6, 15)]
        assert _compute_streak(dates, "FREQ=UNKNOWN", today) == 2


class TestParseByday:
    def test_single_day(self):
        assert _parse_byday("FREQ=WEEKLY;BYDAY=MO") == [0]

    def test_multiple_days(self):
        assert _parse_byday("FREQ=WEEKLY;BYDAY=MO,WE,FR") == [0, 2, 4]

    def test_no_byday_returns_none(self):
        assert _parse_byday("FREQ=WEEKLY") is None

    def test_daily_no_byday_returns_none(self):
        assert _parse_byday("FREQ=DAILY") is None

    def test_case_insensitive(self):
        assert _parse_byday("FREQ=WEEKLY;BYDAY=mo,WE") == [0, 2]


class TestIsDueToday:
    def test_daily_always_due(self):
        assert is_due_today("FREQ=DAILY", date(2026, 6, 22)) is True

    def test_weekly_byday_due_on_matching_day(self):
        # 2026-06-21 is a Sunday.
        assert is_due_today("FREQ=WEEKLY;BYDAY=SU", date(2026, 6, 21)) is True

    def test_weekly_byday_not_due_on_other_day(self):
        # 2026-06-22 is a Monday.
        assert is_due_today("FREQ=WEEKLY;BYDAY=SU", date(2026, 6, 22)) is False

    def test_weekly_no_byday_always_due(self):
        assert is_due_today("FREQ=WEEKLY", date(2026, 6, 22)) is True

    def test_monthly_always_due(self):
        assert is_due_today("FREQ=MONTHLY", date(2026, 6, 22)) is True


class TestIsDoneInCycle:
    def test_empty_dates_returns_false(self):
        assert is_done_in_cycle("FREQ=DAILY", [], date(2026, 7, 20)) is False

    def test_daily_done_only_if_completed_today(self):
        today = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=DAILY", [today], today) is True
        assert is_done_in_cycle("FREQ=DAILY", [today - timedelta(days=1)], today) is False

    def test_weekly_byday_stays_done_through_rest_of_cycle(self):
        # Completed Sunday (its scheduled day); still "done" checking on Monday, since
        # the next occurrence isn't due until the following Sunday.
        sunday = date(2026, 7, 19)
        monday = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=WEEKLY;BYDAY=SU", [sunday], monday) is True

    def test_weekly_byday_not_done_if_last_completion_previous_cycle(self):
        last_sunday = date(2026, 7, 12)
        monday = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=WEEKLY;BYDAY=SU", [last_sunday], monday) is False

    def test_weekly_no_byday_done_if_completed_earlier_same_iso_week(self):
        monday = date(2026, 7, 20)
        wednesday = date(2026, 7, 22)
        assert is_done_in_cycle("FREQ=WEEKLY", [monday], wednesday) is True

    def test_weekly_no_byday_not_done_if_completed_previous_iso_week(self):
        previous_week = date(2026, 7, 13)
        wednesday = date(2026, 7, 22)
        assert is_done_in_cycle("FREQ=WEEKLY", [previous_week], wednesday) is False

    def test_monthly_done_if_completed_earlier_same_month(self):
        today = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=MONTHLY", [date(2026, 7, 3)], today) is True

    def test_monthly_not_done_if_completed_previous_month(self):
        today = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=MONTHLY", [date(2026, 6, 30)], today) is False

    def test_unknown_rule_falls_back_to_exact_day(self):
        today = date(2026, 7, 20)
        assert is_done_in_cycle("FREQ=YEARLY", [today], today) is True
        assert is_done_in_cycle("FREQ=YEARLY", [today - timedelta(days=1)], today) is False


class TestMissedCount:
    # today = Friday 2025-06-06 (weekday 4)
    # week_start = Monday 2025-06-02
    _FRI = date(2025, 6, 6)   # Friday
    _MON = date(2025, 6, 2)
    _TUE = date(2025, 6, 3)
    _WED = date(2025, 6, 4)
    _THU = date(2025, 6, 5)

    # --- WEEKLY with BYDAY ---

    def test_weekly_byday_all_missed(self):
        # MO, WE scheduled; today=Fri; neither done → 2 missed
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,WE", [], self._FRI) == 2

    def test_weekly_byday_one_done(self):
        # MO done, WE missed → 1 missed
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,WE", [self._MON], self._FRI) == 1

    def test_weekly_byday_all_done(self):
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,WE", [self._MON, self._WED], self._FRI) == 0

    def test_weekly_byday_today_scheduled_not_counted(self):
        # FRI is in BYDAY but today hasn't ended → not counted as missed
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,FR", [self._MON], self._FRI) == 0

    def test_weekly_byday_future_day_not_counted(self):
        # Today is Tuesday; WE/FR are future → only MO matters
        tue = date(2025, 6, 3)
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,WE,FR", [], tue) == 1

    def test_weekly_byday_today_is_monday_nothing_missed_yet(self):
        assert _missed_count("FREQ=WEEKLY;BYDAY=MO,WE,FR", [], self._MON) == 0

    # --- WEEKLY without BYDAY ---

    def test_weekly_no_byday_friday_not_done(self):
        assert _missed_count("FREQ=WEEKLY", [], self._FRI) == 1

    def test_weekly_no_byday_friday_done_earlier(self):
        assert _missed_count("FREQ=WEEKLY", [self._MON], self._FRI) == 0

    def test_weekly_no_byday_thursday_not_done(self):
        # Thursday (weekday 3) is below the threshold of 4 → not yet late
        assert _missed_count("FREQ=WEEKLY", [], self._THU) == 0

    def test_weekly_no_byday_early_week_not_late(self):
        assert _missed_count("FREQ=WEEKLY", [], self._WED) == 0

    # --- MONTHLY ---

    def test_monthly_late_in_month_not_done(self):
        late = date(2025, 6, 25)
        assert _missed_count("FREQ=MONTHLY", [], late) == 1

    def test_monthly_late_in_month_done(self):
        late = date(2025, 6, 25)
        assert _missed_count("FREQ=MONTHLY", [date(2025, 6, 10)], late) == 0

    def test_monthly_early_in_month_not_late(self):
        early = date(2025, 6, 10)
        assert _missed_count("FREQ=MONTHLY", [], early) == 0

    # --- DAILY ---

    def test_daily_always_zero(self):
        assert _missed_count("FREQ=DAILY", [], self._FRI) == 0

    # --- Unknown ---

    def test_unknown_rule_returns_zero(self):
        assert _missed_count("FREQ=UNKNOWN", [], self._FRI) == 0
