from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.schemas import WeatherForecast
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
def service(mock_session, mock_weather_client):
    return BriefingSummaryService(session=mock_session, weather_client=mock_weather_client)


class TestBuild:
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
