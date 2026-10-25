from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time
from pydantic import ValidationError

from app.features.organizer.activities.schemas import (
    ActivityCreate,
    ActivityFilters,
    ActivityLogCreate,
    ActivityUpdate,
)
from app.features.organizer.activities.service import (
    ActivityService,
    ActivityStateError,
    ActivityValidationError,
)

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def _activity(id=1, title="Gym", tags=None, **kw):
    defaults = dict(
        id=id, title=title, min_minutes=None, max_minutes=None, context=None, target_per_week=None,
        archived_at=None, created_at=_NOW, updated_at=_NOW, tags=[SimpleNamespace(name=t) for t in (tags or [])],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _log(id=1, activity_id=1, done_at=datetime(2026, 10, 21, 8, 0), minutes=None, note=None):
    return SimpleNamespace(
        id=id, activity_id=activity_id, done_at=done_at, minutes=minutes, note=note, created_at=_NOW, updated_at=_NOW,
    )


@pytest.fixture
def service():
    svc = ActivityService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_last_done.return_value = {}
    svc._repo.count_logs_between.return_value = {}
    return svc


class TestSchemas:
    def test_minimal_activity(self):
        activity = ActivityCreate(title="Read a book")
        assert (activity.min_minutes, activity.context, activity.tags) == (None, None, [])

    @pytest.mark.parametrize("fields", [
        {"title": ""}, {"title": "x", "min_minutes": 0}, {"title": "x", "max_minutes": -1},
        {"title": "x", "min_minutes": 60, "max_minutes": 30}, {"title": "x", "target_per_week": 0},
        {"title": "x", "context": "office"},
    ])
    def test_invalid_values_rejected(self, fields):
        with pytest.raises(ValidationError):
            ActivityCreate(**fields)

    def test_update_cannot_null_the_title(self):
        with pytest.raises(ValidationError):
            ActivityUpdate(title=None)

    def test_update_can_clear_optional_fields(self):
        assert ActivityUpdate(target_per_week=None, context=None).model_dump(exclude_unset=True) == {
            "target_per_week": None, "context": None,
        }

    def test_log_minutes_must_be_positive(self):
        with pytest.raises(ValidationError):
            ActivityLogCreate(minutes=0)


class TestCrud:
    async def test_create(self, service):
        service._repo.create_activity.return_value = _activity(tags=["listen"])
        result = await service.create_activity(ActivityCreate(title="Podcast", tags=["listen"]))
        assert (result.title, result.tags, result.last_done_at) == ("Gym", ["listen"], None)

    async def test_list_adds_last_done(self, service):
        service._repo.get_activities.return_value = [_activity(1), _activity(2, "Book")]
        service._repo.get_last_done.return_value = {2: datetime(2026, 10, 20, 19, 0)}
        result = await service.get_activities(ActivityFilters())
        assert [a.last_done_at for a in result] == [None, datetime(2026, 10, 20, 19, 0)]

    async def test_get_unknown_is_none(self, service):
        service._repo.get_activity.return_value = None
        assert await service.get_activity(9) is None

    async def test_update(self, service):
        service._repo.get_activity.return_value = _activity()
        service._repo.update_activity.return_value = _activity(title="Gym session")
        assert (await service.update_activity(1, ActivityUpdate(title="Gym session"))).title == "Gym session"

    async def test_update_unknown_is_none(self, service):
        service._repo.get_activity.return_value = None
        assert await service.update_activity(9, ActivityUpdate(title="x")) is None

    async def test_update_checks_the_range_against_stored_values(self, service):
        service._repo.get_activity.return_value = _activity(min_minutes=60)
        with pytest.raises(ActivityValidationError, match="max_minutes"):
            await service.update_activity(1, ActivityUpdate(max_minutes=30))
        service._repo.update_activity.assert_not_called()

    async def test_archive_and_unarchive(self, service):
        service._repo.set_archived.return_value = _activity(archived_at=_NOW)
        archived = await service.archive(1)
        assert archived.archived_at is not None
        assert service._repo.set_archived.call_args.args[1] is not None
        service._repo.set_archived.return_value = _activity()
        await service.unarchive(1)
        assert service._repo.set_archived.call_args.args[1] is None

    async def test_archive_unknown_is_none(self, service):
        service._repo.set_archived.return_value = None
        assert await service.archive(9) is None


@freeze_time("2026-10-21 12:00:00")  # 13:00 in Lisbon
class TestLogging:
    async def test_defaults_to_now_in_local_time(self, service):
        service._repo.get_activity.return_value = _activity()
        service._repo.create_log.return_value = _log()
        await service.log(1, ActivityLogCreate(minutes=45, note="Leg day"))
        assert service._repo.create_log.call_args.args[2] == datetime(2026, 10, 21, 13, 0)

    async def test_catch_up_in_the_past(self, service):
        service._repo.get_activity.return_value = _activity()
        service._repo.create_log.return_value = _log()
        await service.log(1, ActivityLogCreate(done_at=datetime(2026, 10, 19, 19, 0)))
        assert service._repo.create_log.call_args.args[2] == datetime(2026, 10, 19, 19, 0)

    async def test_offset_input_is_converted_to_local_time(self, service):
        service._repo.get_activity.return_value = _activity()
        service._repo.create_log.return_value = _log()
        await service.log(1, ActivityLogCreate(done_at=datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)))
        assert service._repo.create_log.call_args.args[2] == datetime(2026, 10, 20, 19, 0)

    async def test_future_logs_are_rejected(self, service):
        service._repo.get_activity.return_value = _activity()
        with pytest.raises(ActivityValidationError, match="future"):
            await service.log(1, ActivityLogCreate(done_at=datetime(2026, 10, 22, 9, 0)))
        service._repo.create_log.assert_not_called()

    async def test_unknown_activity_is_none(self, service):
        service._repo.get_activity.return_value = None
        assert await service.log(9, ActivityLogCreate()) is None

    async def test_archived_activity_cannot_be_logged(self, service):
        service._repo.get_activity.return_value = _activity(archived_at=_NOW)
        with pytest.raises(ActivityStateError, match="archived"):
            await service.log(1, ActivityLogCreate())

    async def test_history_newest_first_with_paging(self, service):
        service._repo.get_activity.return_value = _activity()
        service._repo.get_logs.return_value = [_log(2), _log(1)]
        result = await service.get_history(1, limit=10, offset=5)
        assert [log.id for log in result] == [2, 1]
        service._repo.get_logs.assert_awaited_once_with(1, 10, 5)

    async def test_history_of_unknown_activity_is_none(self, service):
        service._repo.get_activity.return_value = None
        assert await service.get_history(9) is None


@freeze_time("2026-10-21 12:00:00")  # Wednesday
class TestSuggestions:
    async def test_least_recently_done_first_and_never_done_leads(self, service):
        service._repo.get_activities.return_value = [_activity(1, "Gym"), _activity(2, "Podcast"), _activity(3, "Draw")]
        service._repo.get_last_done.return_value = {
            1: datetime(2026, 10, 18, 18, 0), 2: datetime(2026, 10, 12, 20, 0),
        }

        result = await service.get_suggestions()

        assert [s.title for s in result] == ["Draw", "Podcast", "Gym"]
        assert [s.days_since_last_done for s in result] == [None, 9, 3]

    async def test_done_this_week_only_for_activities_with_a_target(self, service):
        service._repo.get_activities.return_value = [
            _activity(1, "Gym", target_per_week=3), _activity(2, "Book"), _activity(3, "Run", target_per_week=2),
        ]
        service._repo.count_logs_between.return_value = {1: 1, 2: 4}

        result = {s.title: s for s in await service.get_suggestions()}

        assert result["Gym"].done_this_week == 1 and result["Gym"].target_per_week == 3
        assert result["Run"].done_this_week == 0
        assert result["Book"].done_this_week is None and result["Book"].target_per_week is None

    async def test_week_window_is_monday_based_in_local_time(self, service):
        service._repo.get_activities.return_value = [_activity(1, target_per_week=3)]
        await service.get_suggestions()
        _, start, end = service._repo.count_logs_between.call_args.args
        assert (start, end) == (datetime(2026, 10, 19, 0, 0), datetime(2026, 10, 26, 0, 0))

    async def test_only_active_activities_are_suggested(self, service):
        await service.get_suggestions()
        assert service._repo.get_activities.call_args.args[0].include_archived is False

    async def test_fields_are_passed_along(self, service):
        service._repo.get_activities.return_value = [
            _activity(5, "Podcast", min_minutes=20, max_minutes=60, context="anywhere", tags=["listen"]),
        ]
        suggestion = (await service.get_suggestions())[0]
        assert (suggestion.min_minutes, suggestion.max_minutes, suggestion.context, suggestion.tags) == (
            20, 60, "anywhere", ["listen"],
        )


@freeze_time("2026-10-21 12:00:00")
class TestStats:
    async def test_stats_use_the_requested_number_of_weeks(self, service):
        service._repo.get_logs_since.return_value = [
            (_log(1, 1, datetime(2026, 10, 20, 18, 0), minutes=60), _activity(1, "Gym", tags=["health"])),
        ]
        stats = await service.get_stats(weeks=2)
        assert [w.week_start for w in stats.weeks] == [date(2026, 10, 12), date(2026, 10, 19)]
        assert (stats.total_count, stats.total_minutes) == (1, 60)
        assert stats.by_tag[0].tag == "health"
        assert service._repo.get_logs_since.call_args.args[0] == datetime(2026, 10, 12, 0, 0)
