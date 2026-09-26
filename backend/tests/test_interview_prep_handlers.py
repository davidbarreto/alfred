from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.interview_candidate import handle_interview_candidate
from app.assistant.commands.handlers.interview_prep import handle_interview_prep
from app.assistant.commands.handlers.interview_story import handle_interview_story
from app.features.organizer.interviews.prep_questions.schemas import StoryLinkRead
from app.features.organizer.interviews.stories.schemas import InterviewStoryRead, StoryStrengthAssessment
from app.features.organizer.interviews.stories.service import StoryAssessmentError

_NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _story_read(id=1) -> InterviewStoryRead:
    return InterviewStoryRead(
        id=id, situation="s", task="t", action="a", result="r", strength=3, tags=[], created_at=_NOW, updated_at=_NOW
    )


class TestStoryAdd:
    async def test_parses_pipe_separated_star(self):
        service = AsyncMock()
        service.create_story.return_value = _story_read()

        await handle_interview_story(
            "add", {"text": "Outage | Restore | Rolled back | Back in 5 min", "strength": "4", "tags": "ops, oncall"}, service
        )

        data = service.create_story.await_args.args[0]
        assert (data.situation, data.task, data.action, data.result) == ("Outage", "Restore", "Rolled back", "Back in 5 min")
        assert data.strength == 4
        assert data.tags == ["ops", "oncall"]

    @pytest.mark.parametrize("text", [None, "only one part", "a | b | c", "a | | c | d"])
    async def test_malformed_star_is_400(self, text):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_story("add", {"text": text}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_out_of_range_strength_is_400_not_500(self):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_story("add", {"text": "a | b | c | d", "strength": "9"}, AsyncMock())
        assert exc.value.status_code == 400


class TestStoryIdArguments:
    @pytest.mark.parametrize("args", [{}, {"id": "abc"}])
    async def test_missing_or_bad_id_is_400(self, args):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_story("assess", args, AsyncMock())
        assert exc.value.status_code == 400

    async def test_assess_llm_failure_is_502(self):
        service = AsyncMock()
        service.assess_strength.side_effect = StoryAssessmentError("LLM call failed")
        with pytest.raises(HTTPException) as exc:
            await handle_interview_story("assess", {"id": "1"}, service)
        assert exc.value.status_code == 502

    async def test_assess_returns_assessment(self):
        service = AsyncMock()
        service.assess_strength.return_value = StoryStrengthAssessment(story_id=1, suggested_strength=4, reasoning="r")
        result = await handle_interview_story("assess", {"id": "1"}, service)
        assert result["suggested_strength"] == 4

    async def test_search_uses_service_query(self):
        service = AsyncMock()
        service.search_stories.return_value = [_story_read()]
        result = await handle_interview_story("search", {"query": " caching "}, service)
        assert result["count"] == 1
        service.search_stories.assert_awaited_once_with("caching")


class TestPrepLink:
    async def test_link_defaults_fit_score_to_3(self):
        service = AsyncMock()
        service.link_story.return_value = StoryLinkRead(question_id=1, story_id=2, fit_score=3)
        await handle_interview_prep("link", {"question_id": "1", "story_id": "2"}, service)
        service.link_story.assert_awaited_once_with(1, 2, 3)

    async def test_missing_story_id_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_prep("link", {"question_id": "1"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_fit_score_out_of_range_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_prep("link", {"question_id": "1", "story_id": "2", "fit_score": "6"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_unknown_question_or_story_is_404(self):
        service = AsyncMock()
        service.link_story.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_interview_prep("link", {"question_id": "1", "story_id": "2"}, service)
        assert exc.value.status_code == 404


class TestCandidate:
    async def test_get_without_id_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_candidate("get", {}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_add_requires_category(self):
        with pytest.raises(HTTPException) as exc:
            await handle_interview_candidate("add", {"text": "How is on-call organised?"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_list_passes_category_and_paginates(self):
        service = AsyncMock()
        service.get_questions.return_value = []
        result = await handle_interview_candidate("list", {"category": "Tech", "limit": "5"}, service)
        service.get_questions.assert_awaited_once_with(category="Tech", limit=6, offset=0)
        assert result["has_next"] is False
