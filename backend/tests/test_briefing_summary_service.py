from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.schemas import HolidayItem, WeatherForecast
from app.features.briefing.summary_service import BriefingSummaryService


def _make_weather() -> WeatherForecast:
    return WeatherForecast(
        temperature_max_c=22.0,
        temperature_min_c=15.0,
        feels_like_max_c=21.0,
        precipitation_probability=20,
        wind_speed_max_kmh=12.0,
        description="Partly cloudy",
        advice=[],
    )


def _make_task_orm(
    id=1,
    title="Fix bug",
    status="TODO",
    priority="HIGH",
    urgency="NORMAL",
    deadline=None,
    tags=None,
):
    task = MagicMock()
    task.id = id
    task.title = title
    task.status = status
    task.priority = priority
    task.urgency = urgency
    task.deadline = deadline
    tag_mocks = []
    for name in (tags or []):
        t = MagicMock()
        t.name = name
        tag_mocks.append(t)
    task.tags = tag_mocks
    return task


def _make_event_orm(
    id=1,
    title="Standup",
    start_datetime=datetime(2026, 6, 23, 9, 0),
    end_datetime=datetime(2026, 6, 23, 9, 30),
    all_day=False,
    location=None,
    description=None,
):
    event = MagicMock()
    event.id = id
    event.title = title
    event.start_datetime = start_datetime
    event.end_datetime = end_datetime
    event.all_day = all_day
    event.location = location
    event.description = description
    return event


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_weather_client():
    client = AsyncMock()
    client.get_daily_forecast.return_value = _make_weather()
    return client


@pytest.fixture
def mock_holiday_client():
    client = AsyncMock()
    client.get_holidays.return_value = []
    return client


@pytest.fixture
def service(mock_session, mock_weather_client, mock_holiday_client):
    return BriefingSummaryService(
        session=mock_session,
        weather_client=mock_weather_client,
        holiday_client=mock_holiday_client,
        contact_service=None,
    )


def _make_track_orm(id=1, code="pt", name="Portuguese", daily_quota=10):
    t = MagicMock()
    t.id = id
    t.code = code
    t.name = name
    t.daily_quota = daily_quota
    return t


class TestBuild:
    @pytest.fixture(autouse=True)
    def _patch_language_repos(self):
        with (
            patch("app.features.briefing.summary_service.LanguageTrackRepository") as MockTrackRepo,
            patch("app.features.briefing.summary_service.ChunkRepository") as MockChunkRepo,
            patch("app.features.briefing.summary_service.LanguageSessionRepository") as MockSessionRepo,
        ):
            MockTrackRepo.return_value.get_tracks = AsyncMock(return_value=[])
            MockChunkRepo.return_value.count_due_for_track = AsyncMock(return_value=0)
            MockSessionRepo.return_value.count_srs_reviews_today = AsyncMock(return_value=0)
            yield MockTrackRepo, MockChunkRepo, MockSessionRepo

    @pytest.mark.asyncio
    async def test_returns_morning_briefing(self, service):
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        assert result.tasks == []
        assert result.events == []
        assert result.weather == _make_weather()
        assert result.holidays == []
        assert result.birthdays == []
        assert isinstance(result.date, date)

    @pytest.mark.asyncio
    async def test_filters_done_tasks(self, service):
        tasks = [
            _make_task_orm(id=1, status="TODO", deadline=datetime(2026, 6, 23)),
            _make_task_orm(id=2, status="DONE", deadline=datetime(2026, 6, 23)),
            _make_task_orm(id=3, status="CANCELLED", deadline=datetime(2026, 6, 23)),
        ]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        assert len(result.tasks) == 1
        assert result.tasks[0].id == 1

    @pytest.mark.asyncio
    async def test_marks_overdue_tasks(self, service):
        tasks = [
            _make_task_orm(id=1, status="TODO", deadline=datetime(2026, 6, 20)),
            _make_task_orm(id=2, status="TODO", deadline=datetime(2026, 6, 25)),
        ]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.briefing.summary_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = MagicMock(date=lambda: date(2026, 6, 23))
            mock_dt.combine = datetime.combine
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        overdue = [t for t in result.tasks if t.is_overdue]
        not_overdue = [t for t in result.tasks if not t.is_overdue]
        assert len(overdue) == 1
        assert overdue[0].id == 1
        assert len(not_overdue) == 1

    @pytest.mark.asyncio
    async def test_marks_today_tasks(self, service):
        tasks = [
            _make_task_orm(id=1, status="TODO", deadline=datetime(2026, 6, 23, 18, 0)),
            _make_task_orm(id=2, status="TODO", deadline=datetime(2026, 6, 25)),
        ]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.briefing.summary_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = MagicMock(date=lambda: date(2026, 6, 23))
            mock_dt.combine = datetime.combine
            mock_dt.max = datetime.max
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        today_task = next(t for t in result.tasks if t.id == 1)
        later_task = next(t for t in result.tasks if t.id == 2)
        assert today_task.is_today is True
        assert later_task.is_today is False

    @pytest.mark.asyncio
    async def test_includes_tasks_within_lookahead_window(self, service):
        tasks = [_make_task_orm(id=1, status="TODO", deadline=datetime(2026, 6, 25))]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.briefing.summary_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = MagicMock(date=lambda: date(2026, 6, 23))
            mock_dt.combine = datetime.combine
            mock_dt.max = datetime.max
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        assert MockTaskRepo.return_value.get_tasks.call_args[0][0].deadline_to == datetime(2026, 6, 25, 23, 59, 59, 999999)
        assert len(result.tasks) == 1

    @pytest.mark.asyncio
    async def test_sorts_tasks_overdue_first(self, service):
        tasks = [
            _make_task_orm(id=1, priority="LOW", deadline=datetime(2026, 6, 23), status="TODO"),
            _make_task_orm(id=2, priority="HIGH", deadline=datetime(2026, 6, 20), status="TODO"),
        ]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.briefing.summary_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = MagicMock(date=lambda: date(2026, 6, 23))
            mock_dt.combine = datetime.combine
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        assert result.tasks[0].id == 2  # overdue HIGH comes first

    @pytest.mark.asyncio
    async def test_events_formatted_with_time(self, service):
        events = [_make_event_orm(title="Standup", start_datetime=datetime(2026, 6, 23, 9, 0), end_datetime=datetime(2026, 6, 23, 9, 30))]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=events)

            result = await service.build()

        assert result.events[0].start_time == "09:00"
        assert result.events[0].end_time == "09:30"
        assert result.events[0].all_day is False

    @pytest.mark.asyncio
    async def test_all_day_events_show_label(self, service):
        events = [_make_event_orm(title="Holiday", all_day=True)]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=events)

            result = await service.build()

        assert result.events[0].start_time == "All day"
        assert result.events[0].end_time is None

    @pytest.mark.asyncio
    async def test_events_within_lookahead_marked_with_days_until(self, service):
        events = [
            _make_event_orm(id=1, title="Standup", start_datetime=datetime(2026, 6, 23, 9, 0), end_datetime=datetime(2026, 6, 23, 9, 30)),
            _make_event_orm(id=2, title="Anniversary", start_datetime=datetime(2026, 6, 24, 0, 0), end_datetime=datetime(2026, 6, 24, 23, 59), all_day=True),
        ]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
            patch("app.features.briefing.summary_service.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = MagicMock(date=lambda: date(2026, 6, 23))
            mock_dt.combine = datetime.combine
            mock_dt.max = datetime.max
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=events)

            result = await service.build()

        today_event = next(e for e in result.events if e.id == 1)
        tomorrow_event = next(e for e in result.events if e.id == 2)
        assert today_event.is_today is True
        assert today_event.days_until == 0
        assert tomorrow_event.is_today is False
        assert tomorrow_event.days_until == 1
        assert result.lookahead_days == 3

    @pytest.mark.asyncio
    async def test_task_tags_extracted(self, service):
        tasks = [_make_task_orm(deadline=datetime(2026, 6, 23), tags=["work", "urgent"])]
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=tasks)
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])

            result = await service.build()

        assert result.tasks[0].tags == ["work", "urgent"]

    @pytest.mark.asyncio
    async def test_includes_holidays_from_client(self, mock_session, mock_weather_client, mock_holiday_client):
        holiday = HolidayItem(name="National Day", local_name="Dia Nacional", country="PT", days_until=0, date=date(2026, 6, 25))
        mock_holiday_client.get_holidays.return_value = [holiday]
        svc = BriefingSummaryService(
            session=mock_session,
            weather_client=mock_weather_client,
            holiday_client=mock_holiday_client,
            contact_service=None,
        )
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            result = await svc.build()

        assert len(result.holidays) == 1
        assert result.holidays[0].country == "PT"

    @pytest.mark.asyncio
    async def test_birthdays_empty_when_no_contact_service(self, service):
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            result = await service.build()

        assert result.birthdays == []

    @pytest.mark.asyncio
    async def test_birthdays_from_contact_service(self, mock_session, mock_weather_client, mock_holiday_client):
        mock_contact_service = AsyncMock()
        mock_contact_service.get_upcoming_birthdays.return_value = [
            {"name": "Alice", "days_until": 3, "date": date(2026, 6, 26)},
        ]
        svc = BriefingSummaryService(
            session=mock_session,
            weather_client=mock_weather_client,
            holiday_client=mock_holiday_client,
            contact_service=mock_contact_service,
        )
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            result = await svc.build()

        assert len(result.birthdays) == 1
        assert result.birthdays[0].name == "Alice"
        assert result.birthdays[0].days_until == 3


class TestLanguageBriefing:
    @pytest.fixture(autouse=True)
    def _patch_base_repos(self):
        with (
            patch("app.features.briefing.summary_service.TaskRepository") as MockTaskRepo,
            patch("app.features.briefing.summary_service.CalendarEventRepository") as MockEventRepo,
        ):
            MockTaskRepo.return_value.get_tasks = AsyncMock(return_value=[])
            MockEventRepo.return_value.get_events = AsyncMock(return_value=[])
            yield

    @pytest.mark.asyncio
    async def test_language_empty_when_no_active_tracks(self, service):
        with (
            patch("app.features.briefing.summary_service.LanguageTrackRepository") as MockTrackRepo,
            patch("app.features.briefing.summary_service.ChunkRepository"),
            patch("app.features.briefing.summary_service.LanguageSessionRepository"),
        ):
            MockTrackRepo.return_value.get_tracks = AsyncMock(return_value=[])
            result = await service.build()

        assert result.language == []

    @pytest.mark.asyncio
    async def test_language_includes_due_count_per_track(self, service):
        track = _make_track_orm(id=1, code="pt", name="Portuguese", daily_quota=10)
        with (
            patch("app.features.briefing.summary_service.LanguageTrackRepository") as MockTrackRepo,
            patch("app.features.briefing.summary_service.ChunkRepository") as MockChunkRepo,
            patch("app.features.briefing.summary_service.LanguageSessionRepository") as MockSessionRepo,
        ):
            MockTrackRepo.return_value.get_tracks = AsyncMock(return_value=[track])
            MockChunkRepo.return_value.count_due_for_track = AsyncMock(return_value=7)
            MockSessionRepo.return_value.count_srs_reviews_today = AsyncMock(return_value=0)
            result = await service.build()

        assert len(result.language) == 1
        item = result.language[0]
        assert item.code == "pt"
        assert item.name == "Portuguese"
        assert item.due_count == 7
        assert item.completed_today == 0
        assert item.daily_quota == 10
        assert item.quota_met is False

    @pytest.mark.asyncio
    async def test_language_quota_met_when_completed_equals_quota(self, service):
        track = _make_track_orm(id=1, code="es", name="Spanish", daily_quota=5)
        with (
            patch("app.features.briefing.summary_service.LanguageTrackRepository") as MockTrackRepo,
            patch("app.features.briefing.summary_service.ChunkRepository") as MockChunkRepo,
            patch("app.features.briefing.summary_service.LanguageSessionRepository") as MockSessionRepo,
        ):
            MockTrackRepo.return_value.get_tracks = AsyncMock(return_value=[track])
            MockChunkRepo.return_value.count_due_for_track = AsyncMock(return_value=0)
            MockSessionRepo.return_value.count_srs_reviews_today = AsyncMock(return_value=5)
            result = await service.build()

        assert result.language[0].quota_met is True
        assert result.language[0].completed_today == 5

    @pytest.mark.asyncio
    async def test_language_multiple_tracks(self, service):
        tracks = [
            _make_track_orm(id=1, code="pt", name="Portuguese", daily_quota=10),
            _make_track_orm(id=2, code="es", name="Spanish", daily_quota=5),
        ]
        with (
            patch("app.features.briefing.summary_service.LanguageTrackRepository") as MockTrackRepo,
            patch("app.features.briefing.summary_service.ChunkRepository") as MockChunkRepo,
            patch("app.features.briefing.summary_service.LanguageSessionRepository") as MockSessionRepo,
        ):
            MockTrackRepo.return_value.get_tracks = AsyncMock(return_value=tracks)
            MockChunkRepo.return_value.count_due_for_track = AsyncMock(side_effect=[3, 8])
            MockSessionRepo.return_value.count_srs_reviews_today = AsyncMock(side_effect=[2, 0])
            result = await service.build()

        assert len(result.language) == 2
        assert result.language[0].code == "pt"
        assert result.language[0].due_count == 3
        assert result.language[0].completed_today == 2
        assert result.language[1].code == "es"
        assert result.language[1].due_count == 8
