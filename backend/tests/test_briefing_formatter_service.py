from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.formatter_service import BriefingFormatterService, _build_context
from app.features.briefing.schemas import (
    BirthdayItem,
    EventBriefItem,
    FormattedBriefing,
    HolidayItem,
    LanguageBriefItem,
    MorningBriefing,
    ShoppingBriefItem,
    TaskBriefItem,
    WeatherForecast,
)
from app.shared.llm import LlmResponse


def _make_briefing(**kwargs) -> MorningBriefing:
    defaults = dict(
        date=date(2026, 6, 23),
        tasks=[],
        events=[],
        holidays=[],
        birthdays=[],
        weather=WeatherForecast(
            temperature_max_c=22.0,
            temperature_min_c=15.0,
            feels_like_max_c=21.0,
            precipitation_probability=20,
            wind_speed_max_kmh=12.0,
            description="Partly cloudy",
            advice=[],
        ),
    )
    defaults.update(kwargs)
    return MorningBriefing(**defaults)


def _make_task_item(**kwargs) -> TaskBriefItem:
    defaults = dict(
        id=1,
        title="Fix bug",
        priority="HIGH",
        urgency="NORMAL",
        deadline=datetime(2026, 6, 23, 23, 59),
        tags=[],
        is_overdue=False,
        is_today=True,
    )
    defaults.update(kwargs)
    return TaskBriefItem(**defaults)


def _make_event_item(**kwargs) -> EventBriefItem:
    defaults = dict(
        id=1,
        title="Standup",
        date=date(2026, 6, 23),
        start_time="09:00",
        end_time="09:30",
        location=None,
        description=None,
        all_day=False,
        is_today=True,
        days_until=0,
    )
    defaults.update(kwargs)
    return EventBriefItem(**defaults)


def _make_shopping_item(**kwargs) -> ShoppingBriefItem:
    defaults = dict(
        id=1,
        name="Milk",
        category="grocery",
        priority="need",
        quantity=None,
        unit=None,
        store=None,
    )
    defaults.update(kwargs)
    return ShoppingBriefItem(**defaults)


class TestBuildContext:
    def test_includes_date(self):
        briefing = _make_briefing()
        context = _build_context(briefing)
        assert "Tuesday, 23 June 2026" in context

    def test_includes_task_title(self):
        briefing = _make_briefing(tasks=[_make_task_item(title="Deploy release")])
        context = _build_context(briefing)
        assert "Deploy release" in context

    def test_marks_overdue_tasks(self):
        briefing = _make_briefing(tasks=[_make_task_item(is_overdue=True)])
        context = _build_context(briefing)
        assert "OVERDUE" in context

    def test_no_tasks_message(self):
        briefing = _make_briefing(tasks=[])
        context = _build_context(briefing)
        assert "No tasks due today" in context

    def test_includes_event_time(self):
        briefing = _make_briefing(events=[_make_event_item(start_time="10:00", end_time="11:00")])
        context = _build_context(briefing)
        assert "10:00 - 11:00" in context

    def test_includes_weather_description(self):
        briefing = _make_briefing()
        context = _build_context(briefing)
        assert "Partly cloudy" in context

    def test_includes_weather_advice(self):
        briefing = _make_briefing(
            weather=WeatherForecast(
                temperature_max_c=10.0,
                temperature_min_c=5.0,
                feels_like_max_c=8.0,
                precipitation_probability=60,
                wind_speed_max_kmh=15.0,
                description="Rainy",
                advice=["Take an umbrella", "Take a coat"],
            )
        )
        context = _build_context(briefing)
        assert "Take an umbrella" in context
        assert "Take a coat" in context

    def test_all_day_event_label(self):
        briefing = _make_briefing(
            events=[_make_event_item(start_time="All day", end_time=None, all_day=True)]
        )
        context = _build_context(briefing)
        assert "All day" in context

    def test_includes_holiday_today(self):
        briefing = _make_briefing(
            holidays=[HolidayItem(name="National Day", local_name="Dia Nacional", country="PT", days_until=0, date=date(2026, 6, 23))]
        )
        context = _build_context(briefing)
        assert "Dia Nacional" in context
        assert "PT" in context
        assert "today!" in context

    def test_includes_holiday_tomorrow(self):
        briefing = _make_briefing(
            holidays=[HolidayItem(name="National Day", local_name="Dia Nacional", country="PT", days_until=1, date=date(2026, 6, 24))]
        )
        context = _build_context(briefing)
        assert "Dia Nacional" in context
        assert "tomorrow" in context

    def test_includes_holiday_in_future(self):
        briefing = _make_briefing(
            holidays=[HolidayItem(name="National Day", local_name="Dia Nacional", country="PT", days_until=5, date=date(2026, 6, 28))]
        )
        context = _build_context(briefing)
        assert "Dia Nacional" in context
        assert "in 5 days" in context

    def test_no_holidays_section_when_empty(self):
        briefing = _make_briefing(holidays=[])
        context = _build_context(briefing)
        assert "Upcoming holidays" not in context

    def test_no_language_section_when_empty(self):
        briefing = _make_briefing(language=[])
        context = _build_context(briefing)
        assert "Language practice" not in context

    def test_language_due_count_in_context(self):
        lang = LanguageBriefItem(
            track_id=1, code="pt", name="Portuguese",
            due_count=7, completed_today=0, daily_quota=10, quota_met=False,
        )
        briefing = _make_briefing(language=[lang])
        context = _build_context(briefing)
        assert "Language practice" in context
        assert "Portuguese" in context
        assert "7 reviews due" in context

    def test_language_partial_progress_in_context(self):
        lang = LanguageBriefItem(
            track_id=1, code="pt", name="Portuguese",
            due_count=5, completed_today=3, daily_quota=10, quota_met=False,
        )
        briefing = _make_briefing(language=[lang])
        context = _build_context(briefing)
        assert "3/10 done" in context
        assert "5 still due" in context

    def test_language_quota_met_in_context(self):
        lang = LanguageBriefItem(
            track_id=1, code="pt", name="Portuguese",
            due_count=0, completed_today=10, daily_quota=10, quota_met=True,
        )
        briefing = _make_briefing(language=[lang])
        context = _build_context(briefing)
        assert "quota met" in context
        assert "10/10" in context

    def test_no_shopping_section_when_empty(self):
        briefing = _make_briefing(shopping=[])
        context = _build_context(briefing)
        assert "Shopping list" not in context

    def test_shopping_item_name_in_context(self):
        briefing = _make_briefing(shopping=[_make_shopping_item(name="Olive oil")])
        context = _build_context(briefing)
        assert "Shopping list — pending items (1)" in context
        assert "Olive oil" in context

    def test_shopping_quantity_and_unit_in_context(self):
        briefing = _make_briefing(shopping=[_make_shopping_item(quantity=2.0, unit="L")])
        context = _build_context(briefing)
        assert "x2 L" in context

    def test_shopping_store_in_context(self):
        briefing = _make_briefing(shopping=[_make_shopping_item(store="Continente")])
        context = _build_context(briefing)
        assert "at Continente" in context

    def test_birthday_today(self):
        briefing = _make_briefing(
            birthdays=[BirthdayItem(name="Alice", days_until=0, date=date(2026, 6, 23))]
        )
        context = _build_context(briefing)
        assert "Alice" in context
        assert "today!" in context

    def test_birthday_tomorrow(self):
        briefing = _make_briefing(
            birthdays=[BirthdayItem(name="Bob", days_until=1, date=date(2026, 6, 24))]
        )
        context = _build_context(briefing)
        assert "Bob" in context
        assert "tomorrow" in context

    def test_birthday_in_n_days(self):
        briefing = _make_briefing(
            birthdays=[BirthdayItem(name="Carol", days_until=5, date=date(2026, 6, 28))]
        )
        context = _build_context(briefing)
        assert "Carol" in context
        assert "in 5 days" in context


class TestBriefingFormatterService:
    @pytest.fixture
    def mock_llm(self):
        provider = MagicMock()
        provider.provider = "google"
        provider.model = "gemini-2.0-flash"
        provider.complete = AsyncMock(
            return_value=LlmResponse(text="Good morning! Here is your briefing.", tokens_input=100, tokens_output=50, finish_reason="STOP")
        )
        return provider

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_llm, mock_session):
        svc = BriefingFormatterService(llm_provider=mock_llm, session=mock_session)
        svc._repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_returns_formatted_briefing(self, service):
        with patch("app.features.briefing.formatter_service.create_llm_call", new_callable=AsyncMock):
            result = await service.format(_make_briefing())

        assert isinstance(result, FormattedBriefing)
        assert result.text == "Good morning! Here is your briefing."
        assert result.date == date(2026, 6, 23)

    @pytest.mark.asyncio
    async def test_logs_llm_call(self, service, mock_session):
        with patch("app.features.briefing.formatter_service.create_llm_call", new_callable=AsyncMock) as mock_log:
            await service.format(_make_briefing())

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert call_kwargs["feature"] == "morning_briefing"
        assert call_kwargs["provider"] == "google"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_llm_response(self, service, mock_llm):
        mock_llm.complete.return_value = LlmResponse(
            text="  Briefing text with spaces  \n",
            tokens_input=10,
            tokens_output=5,
            finish_reason="STOP",
        )
        with patch("app.features.briefing.formatter_service.create_llm_call", new_callable=AsyncMock):
            result = await service.format(_make_briefing())

        assert result.text == "Briefing text with spaces"

    @pytest.mark.asyncio
    async def test_commits_session(self, service, mock_session):
        with patch("app.features.briefing.formatter_service.create_llm_call", new_callable=AsyncMock):
            await service.format(_make_briefing())

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_generated_text(self, service):
        with patch("app.features.briefing.formatter_service.create_llm_call", new_callable=AsyncMock):
            await service.format(_make_briefing())

        service._repo.upsert_briefing.assert_called_once_with(
            date(2026, 6, 23), "Good morning! Here is your briefing."
        )

    @pytest.mark.asyncio
    async def test_get_saved_returns_none_when_not_found(self, service):
        service._repo.get_briefing_by_date.return_value = None

        result = await service.get_saved(date(2026, 6, 23))

        assert result is None
        service._repo.get_briefing_by_date.assert_called_once_with(date(2026, 6, 23))

    @pytest.mark.asyncio
    async def test_get_saved_returns_formatted_briefing(self, service):
        saved = MagicMock()
        saved.date = date(2026, 6, 23)
        saved.text = "Saved briefing text."
        service._repo.get_briefing_by_date.return_value = saved

        result = await service.get_saved(date(2026, 6, 23))

        assert isinstance(result, FormattedBriefing)
        assert result.date == date(2026, 6, 23)
        assert result.text == "Saved briefing text."

    @pytest.mark.asyncio
    async def test_get_saved_defaults_to_today(self, service):
        service._repo.get_briefing_by_date.return_value = None

        await service.get_saved()

        looked_up = service._repo.get_briefing_by_date.call_args[0][0]
        assert isinstance(looked_up, date)
