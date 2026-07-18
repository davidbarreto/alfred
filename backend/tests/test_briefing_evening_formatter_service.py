from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.evening_formatter_service import EveningDigestFormatterService, _build_context
from app.features.briefing.schemas import EveningDigest, EveningEventItem, EveningNoteItem, EveningTaskItem, FormattedBriefing, WinItem
from app.shared.llm import LlmResponse


def _make_digest(**kwargs) -> EveningDigest:
    defaults = dict(
        date=date(2026, 7, 18),
        wins=[],
        tasks=[],
        tomorrow_events=[],
        notes=[],
    )
    defaults.update(kwargs)
    return EveningDigest(**defaults)


def _make_task_item(**kwargs) -> EveningTaskItem:
    defaults = dict(
        id=1, title="Water plants", priority="LOW", urgency="NORMAL",
        deadline=None, tags=[], is_overdue=False,
    )
    defaults.update(kwargs)
    return EveningTaskItem(**defaults)


def _make_event_item(**kwargs) -> EveningEventItem:
    defaults = dict(
        id=1, title="Dentist", date=date(2026, 7, 19),
        start_time="09:00", end_time="09:30", location=None, all_day=False,
    )
    defaults.update(kwargs)
    return EveningEventItem(**defaults)


class TestBuildContext:
    def test_includes_wins(self):
        digest = _make_digest(wins=[WinItem(title="Paid rent")])
        context = _build_context(digest)
        assert "Paid rent" in context
        assert "Completed today (1)" in context

    def test_no_wins_message(self):
        digest = _make_digest(wins=[])
        context = _build_context(digest)
        assert "Nothing marked done today" in context

    def test_includes_open_task(self):
        digest = _make_digest(tasks=[_make_task_item(title="Fix bug")])
        context = _build_context(digest)
        assert "Fix bug" in context

    def test_marks_overdue_task(self):
        digest = _make_digest(tasks=[_make_task_item(is_overdue=True)])
        context = _build_context(digest)
        assert "OVERDUE" in context

    def test_no_open_tasks_message(self):
        digest = _make_digest(tasks=[])
        context = _build_context(digest)
        assert "No open tasks" in context

    def test_includes_tomorrow_event(self):
        digest = _make_digest(tomorrow_events=[_make_event_item(title="Dentist")])
        context = _build_context(digest)
        assert "Dentist" in context

    def test_no_events_tomorrow_message(self):
        digest = _make_digest(tomorrow_events=[])
        context = _build_context(digest)
        assert "No events tomorrow" in context

    def test_includes_notes_as_context(self):
        digest = _make_digest(notes=[EveningNoteItem(id=1, title="Trip idea", content="")])
        context = _build_context(digest)
        assert "Trip idea" in context
        assert "context only" in context

    def test_no_notes_section_when_empty(self):
        digest = _make_digest(notes=[])
        context = _build_context(digest)
        assert "Recent notes" not in context


class TestEveningDigestFormatterService:
    @pytest.fixture
    def mock_llm(self):
        provider = MagicMock()
        provider.provider = "google"
        provider.model = "gemini-2.0-flash"
        provider.complete = AsyncMock(
            return_value=LlmResponse(text="Nice work today. Tomorrow, start with the report.", tokens_input=50, tokens_output=20, finish_reason="STOP")
        )
        return provider

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_llm, mock_session):
        svc = EveningDigestFormatterService(llm_provider=mock_llm, session=mock_session)
        svc._repo = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_returns_formatted_digest_with_header(self, service):
        with patch("app.features.briefing.evening_formatter_service.create_llm_call", new_callable=AsyncMock):
            result = await service.format(_make_digest())

        assert isinstance(result, FormattedBriefing)
        assert result.text == "🌙 Evening Digest\n\nNice work today. Tomorrow, start with the report."
        assert result.date == date(2026, 7, 18)

    @pytest.mark.asyncio
    async def test_saves_with_evening_type(self, service):
        with patch("app.features.briefing.evening_formatter_service.create_llm_call", new_callable=AsyncMock):
            await service.format(_make_digest())

        service._repo.upsert_briefing.assert_called_once_with(
            date(2026, 7, 18), "evening", "🌙 Evening Digest\n\nNice work today. Tomorrow, start with the report."
        )

    @pytest.mark.asyncio
    async def test_logs_llm_call_with_evening_feature(self, service):
        with patch("app.features.briefing.evening_formatter_service.create_llm_call", new_callable=AsyncMock) as mock_log:
            await service.format(_make_digest())

        assert mock_log.call_args[1]["feature"] == "evening_digest"

    @pytest.mark.asyncio
    async def test_get_saved_returns_none_when_not_found(self, service):
        service._repo.get_briefing_by_date.return_value = None

        result = await service.get_saved(date(2026, 7, 18))

        assert result is None
        service._repo.get_briefing_by_date.assert_called_once_with(date(2026, 7, 18), "evening")

    @pytest.mark.asyncio
    async def test_get_saved_returns_formatted_digest(self, service):
        saved = MagicMock()
        saved.date = date(2026, 7, 18)
        saved.text = "Saved digest text."
        service._repo.get_briefing_by_date.return_value = saved

        result = await service.get_saved(date(2026, 7, 18))

        assert isinstance(result, FormattedBriefing)
        assert result.text == "Saved digest text."
