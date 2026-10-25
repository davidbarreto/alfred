import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.features.language.sessions.service import SessionService as LanguageSessionService
from app.features.organizer.calendar_events.schemas import EventFilters, EventRead
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.routines.expansion import expand_scheduled_steps, localize, scheduled_dates
from app.features.organizer.routines.schemas import RoutineRead
from app.features.organizer.routines.service import RoutineService
from app.features.organizer.shopping.schemas import ShoppingItemFilters
from app.features.organizer.shopping.service import ShoppingService
from app.features.organizer.tasks.schemas import TaskFilters, TaskRead
from app.features.organizer.tasks.service import TaskService
from app.features.planning import timeline
from app.features.planning.saved_plans.service import SavedPlanService
from app.features.planning.schemas import (
    DayPlanRead,
    DayRead,
    LanguageProgress,
    OfficeSummary,
    RecurringTaskItem,
    RoutineBlock,
    ShoppingSection,
    StudyItemRef,
    StudyPlanSummary,
    StudySection,
    SuggestedRun,
    TaskItem,
    WorkSummary,
)
from app.features.planning.settings_service import PlanningSettingsService
from app.features.study.plans.service import StudyPlanService
from app.shared.timezone import local_now, local_timezone_name, local_today

logger = logging.getLogger(__name__)

MAX_DAYS = 7
_TASK_CAP = 30
_STUDY_ITEMS_PER_PLAN = 5
_DUE_LOOKAHEAD_DAYS = 3
_EVENT_LIMIT = 500
_ASSUMED_ESTIMATE_MINUTES = 30
_ASSUMED_CONTEXT = "anywhere"
_SHOPPING_RUN_MINUTES = 45
_UTC = timezone.utc


class DayPlanService:
    """Read-only aggregation of Alfred's data for planning a day or a week. It never schedules anything."""

    def __init__(
        self,
        event_service: CalendarEventService,
        routine_service: RoutineService,
        task_service: TaskService,
        study_service: StudyPlanService,
        language_service: LanguageSessionService,
        shopping_service: ShoppingService,
        settings_service: PlanningSettingsService,
        saved_plan_service: SavedPlanService,
    ) -> None:
        self._events = event_service
        self._routines = routine_service
        self._tasks = task_service
        self._study = study_service
        self._language = language_service
        self._shopping = shopping_service
        self._settings = settings_service
        self._saved = saved_plan_service

    async def get_plan(
        self, start: date | None = None, days: int = 1, work_minutes: int | None = None
    ) -> DayPlanRead:
        first = start or local_today()
        dates = [first + timedelta(days=i) for i in range(days)]
        settings = await self._settings.get()
        warnings: list[str] = []

        events = await self._load_events(dates)
        routines_by_id, scheduled_routines, note_titles = await self._load_routines(events)
        day_reads = [
            self._build_day(d, events, routines_by_id, scheduled_routines, note_titles, settings, work_minutes, warnings)
            for d in dates
        ]
        office = await self._office_summary(first, settings)
        tasks = await self._task_sections(dates, warnings)

        plan = DayPlanRead(
            date=first.isoformat(),
            timezone=local_timezone_name(),
            preferences=_preferences(settings),
            office=office,
            overdue_tasks=tasks["overdue"],
            due_tasks=tasks["due"],
            recurring_tasks=tasks["recurring"],
            backlog_tasks=tasks["backlog"],
            study=await self._study_section(),
            shopping=await self._shopping_section(),
            saved_plan=await self._saved_plans(dates),
            warnings=warnings,
        )
        if days == 1:
            day = day_reads[0]
            plan.work, plan.timeline, plan.routine_blocks, plan.all_day = (
                day.work, day.timeline, day.routine_blocks, day.all_day,
            )
        else:
            plan.days = day_reads
        logger.debug("Day plan built: first=%s days=%d warnings=%d", first, days, len(warnings))
        return plan

    # --- events, routines, days -------------------------------------------------------------

    async def _load_events(self, dates: list[date]) -> list[EventRead]:
        filters = EventFilters(
            limit=_EVENT_LIMIT,
            start_from=datetime.combine(dates[0], datetime.min.time()),
            start_to=datetime.combine(dates[-1], datetime.max.time().replace(microsecond=0)),
        )
        return await self._events.get_events(filters)

    async def _load_routines(
        self, events: list[EventRead]
    ) -> tuple[dict[int, RoutineRead], list[RoutineRead], dict[int, str]]:
        routine_ids = sorted({e.routine_id for e in events if e.routine_id is not None})
        attached = await self._routines.get_routines_by_ids(routine_ids)
        scheduled = await self._routines.get_active_scheduled_routines()
        note_ids = sorted({
            step.checklist_note_id for routine in (*attached, *scheduled) for step in routine.steps
            if step.checklist_note_id is not None
        })
        note_titles = await self._routines.get_note_titles(note_ids) if note_ids else {}
        return {r.id: r for r in attached}, scheduled, note_titles

    def _build_day(
        self,
        day: date,
        events: list[EventRead],
        routines_by_id: dict[int, RoutineRead],
        scheduled_routines: list[RoutineRead],
        note_titles: dict[int, str],
        settings: Any,
        work_minutes: int | None,
        warnings: list[str],
    ) -> DayRead:
        items, overlaps = timeline.build_timeline(events, routines_by_id, note_titles, day)
        warnings.extend(overlaps)
        blocks: list[RoutineBlock] = []
        for routine in scheduled_routines:
            try:
                runs_today = day in scheduled_dates(routine.recurrence_rule, routine.starts_on, day, day)
            except ValueError as exc:
                warnings.append(f"Routine {routine.id} ({routine.name}) has an invalid recurrence rule: {exc}")
                continue
            if runs_today:
                windows = expand_scheduled_steps(routine.steps, [day])
                blocks.extend(timeline.routine_blocks_for(routine.name, windows, note_titles))
        target = settings.work_target_minutes if work_minutes is None else work_minutes
        committed = timeline.committed_work_minutes(events, day, settings.work_tag)
        return DayRead(
            date=day.isoformat(),
            timeline=items,
            routine_blocks=blocks,
            all_day=timeline.all_day_for_day(events, day),
            work=WorkSummary(
                target_minutes=target,
                committed_minutes=committed,
                remaining_minutes=max(0, target - committed),
                preferred_windows=settings.preferred_work_windows or None,
            ),
        )

    async def _office_summary(self, first: date, settings: Any) -> OfficeSummary | None:
        if settings.office_days_per_week is None:
            return None
        monday, sunday = timeline.week_bounds(first)
        events = await self._events.get_events(
            EventFilters(
                limit=_EVENT_LIMIT,
                tags=[settings.office_tag],
                start_from=datetime.combine(monday, datetime.min.time()),
                start_to=datetime.combine(sunday, datetime.max.time().replace(microsecond=0)),
            )
        )
        min_minutes = settings.office_min_minutes or 0
        planned = timeline.office_days(events, settings.office_tag, min_minutes)
        return OfficeSummary(
            goal_per_week=settings.office_days_per_week,
            min_minutes=min_minutes,
            planned_this_week=len(planned),
            days_left_in_week=timeline.days_left_in_week(first),
        )

    # --- tasks -----------------------------------------------------------------------------

    async def _task_sections(self, dates: list[date], warnings: list[str]) -> dict[str, list]:
        tasks = await self._tasks.get_tasks(TaskFilters(status="ACTIVE", limit=_EVENT_LIMIT))
        range_start, _ = timeline.day_bounds(dates[0])
        _, range_end = timeline.day_bounds(dates[-1])
        boundary = max(local_now().astimezone(_UTC), range_start.astimezone(_UTC))
        lookahead_end = (range_end + timedelta(days=_DUE_LOOKAHEAD_DAYS)).astimezone(_UTC)
        range_end_utc = range_end.astimezone(_UTC)
        today = local_today()

        overdue: list[tuple[datetime, TaskRead]] = []
        due: list[tuple[datetime, TaskRead]] = []
        backlog: list[TaskRead] = []
        recurring: list[RecurringTaskItem] = []

        for task in tasks:
            available = localize(task.available_from).astimezone(_UTC) if task.available_from else None
            if available is not None and available >= range_end_utc:
                continue  # cannot be placed yet; it shows up in a later plan
            if task.recurrence_rule:
                item = _recurring_item(task, dates, today)
                if item is not None:
                    recurring.append(item)
                continue
            if task.deadline is None:
                backlog.append(task)
                continue
            deadline = localize(task.deadline).astimezone(_UTC)
            if deadline < boundary:
                overdue.append((deadline, task))
            elif deadline < lookahead_end:
                due.append((deadline, task))

        overdue_items = [_task_item(t) for _, t in sorted(overdue, key=lambda pair: pair[0])[:_TASK_CAP]]
        due_items = [_task_item(t) for _, t in sorted(due, key=lambda pair: pair[0])[:_TASK_CAP]]
        backlog_items = [_task_item(t) for t in backlog[:_TASK_CAP]]
        recurring = recurring[:_TASK_CAP]
        warnings.extend(_assumption_warnings([*overdue_items, *due_items, *recurring, *backlog_items]))
        return {"overdue": overdue_items, "due": due_items, "recurring": recurring, "backlog": backlog_items}

    # --- study, language, shopping ---------------------------------------------------------

    async def _study_section(self) -> StudySection:
        overview = await self._study.get_overview()
        plans = []
        for plan in overview.active:
            open_items = [StudyItemRef(item_id=i.id, description=i.description) for i in plan.items if not i.is_done]
            if not open_items:
                continue
            plans.append(
                StudyPlanSummary(
                    plan_id=plan.id, title=plan.title, goal=plan.goal, priority=plan.priority,
                    tags=plan.tags or None, open_items=open_items[:_STUDY_ITEMS_PER_PLAN],
                )
            )
        progress = await self._language.get_daily_progress()
        language = [
            LanguageProgress(
                track=p.track_code, daily_quota=p.daily_quota, done_today=p.completed_today, quota_met=p.quota_met
            )
            for p in progress
        ]
        return StudySection(plans=plans, language=language)

    async def _saved_plans(self, dates: list[date]) -> list[dict[str, Any]] | None:
        plans = await self._saved.get_saved(dates[0], dates[-1])
        if not plans:
            return None
        hidden = {"id", "source", "created_at", "updated_at", "archived_at"}
        return [p.model_dump(mode="json", exclude=hidden, exclude_none=True) for p in plans]

    async def _shopping_section(self) -> ShoppingSection | None:
        pending = await self._shopping.list_items(ShoppingItemFilters(status="pending", limit=500))
        due_recurring = await self._shopping.list_due_recurrences()
        if not pending and not due_recurring:
            return None
        return ShoppingSection(
            pending_items=len(pending),
            due_recurring=len(due_recurring),
            suggested_run=SuggestedRun(estimate_minutes=_SHOPPING_RUN_MINUTES, context="out"),
        )


def _preferences(settings: Any) -> dict[str, Any]:
    prefs = {
        "wake_time": settings.wake_time,
        "sleep_time": settings.sleep_time,
        "work_target_minutes": settings.work_target_minutes,
        "preferred_work_windows": settings.preferred_work_windows or None,
    }
    return {k: v for k, v in prefs.items() if v is not None}


def _task_item(task: TaskRead) -> TaskItem:
    return TaskItem(**_task_fields(task))


def _task_fields(task: TaskRead) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "estimate_minutes": task.estimate_minutes,
        "context": task.context,
        "tags": task.tags or None,
        "priority": task.priority,
        "urgency": task.urgency,
        "deadline": timeline.iso_local(localize(task.deadline)) if task.deadline else None,
        "available_from": timeline.iso_local(localize(task.available_from)) if task.available_from else None,
        "created_at": timeline.iso_local(localize(task.created_at)) if task.created_at else None,
    }


def _recurring_item(task: TaskRead, dates: list[date], today: date) -> RecurringTaskItem | None:
    rule = task.recurrence_rule
    done_now = task.is_done_in_cycle and today in dates
    if timeline.is_flexible_cadence(rule):
        if done_now:
            return None
        return RecurringTaskItem(**_task_fields(task), flexible=True)
    due_dates = [d for d in timeline.recurring_due_dates(rule, dates) if not (done_now and d == today)]
    if not due_dates:
        return None
    return RecurringTaskItem(**_task_fields(task), due_dates=[d.isoformat() for d in due_dates])


def _assumption_warnings(items: list[TaskItem]) -> list[str]:
    missing_estimate = [t.id for t in items if t.estimate_minutes is None]
    missing_context = [t.id for t in items if t.context is None]
    both = sorted(set(missing_estimate) & set(missing_context))
    only_estimate = sorted(set(missing_estimate) - set(both))
    only_context = sorted(set(missing_context) - set(both))
    assumed = f"assumed {_ASSUMED_ESTIMATE_MINUTES} min / {_ASSUMED_CONTEXT}"
    warnings = []
    if both:
        warnings.append(f"{_ids(both)} no estimate and no context; {assumed}.")
    if only_estimate:
        warnings.append(f"{_ids(only_estimate)} no estimate; assumed {_ASSUMED_ESTIMATE_MINUTES} min.")
    if only_context:
        warnings.append(f"{_ids(only_context)} no context; assumed {_ASSUMED_CONTEXT}.")
    return warnings


def _ids(ids: list[int]) -> str:
    label = "Task" if len(ids) == 1 else "Tasks"
    verb = "has" if len(ids) == 1 else "have"
    return f"{label} {', '.join(str(i) for i in ids)} {verb}"
