from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryUpdate
from app.features.organizer.interviews.stories.service import InterviewStoryService, StoryAssessmentError
from app.features.organizer.interviews.stories.tables import InterviewStory, InterviewStoryTag
from app.shared.llm import LlmResponse

_NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _story(id=1, strength=3, tags=()) -> InterviewStory:
    return InterviewStory(
        id=id,
        situation="Legacy service kept timing out",
        task="Stabilise it before peak season",
        action="Added caching and a circuit breaker",
        result="p99 latency dropped by half",
        strength=strength,
        tags=[InterviewStoryTag(id=i + 1, story_id=id, tag=t) for i, t in enumerate(tags)],
        created_at=_NOW,
        updated_at=_NOW,
    )


def _llm(text: str) -> MagicMock:
    provider = MagicMock()
    provider.provider = "google"
    provider.model = "gemini-test"
    provider.complete = AsyncMock(
        return_value=LlmResponse(text=text, tokens_input=10, tokens_output=5, finish_reason="stop")
    )
    return provider


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    svc = InterviewStoryService(AsyncMock(), _llm("{}"))
    svc._repo = mock_repo
    return svc


class TestCreateStory:
    async def test_passes_tags_and_returns_read_model(self, service, mock_repo):
        mock_repo.create_story.return_value = _story(strength=4, tags=["Leadership"])
        data = InterviewStoryCreate(
            situation="s", task="t", action="a", result="r", strength=4, tags=["Leadership"]
        )

        result = await service.create_story(data)

        assert result.id == 1
        assert result.created_at == _NOW
        assert [t.tag for t in result.tags] == ["Leadership"]
        assert mock_repo.create_story.call_args.kwargs["tags"] == ["Leadership"]


class TestTagNormalization:
    def test_strips_blanks_and_duplicates(self):
        data = InterviewStoryCreate(
            situation="s", task="t", action="a", result="r", tags=[" Leadership", "", "Leadership", "Conflict "]
        )
        assert data.tags == ["Leadership", "Conflict"]

    def test_rejects_overlong_tag(self):
        with pytest.raises(ValidationError):
            InterviewStoryCreate(situation="s", task="t", action="a", result="r", tags=["x" * 101])


class TestUpdateStory:
    async def test_sends_only_set_fields_and_tags_separately(self, service, mock_repo):
        mock_repo.update_story.return_value = _story(strength=5, tags=["Leadership"])

        result = await service.update_story(1, InterviewStoryUpdate(strength=5, tags=["Leadership"]))

        assert result is not None and result.strength == 5
        mock_repo.update_story.assert_awaited_once_with(1, fields={"strength": 5}, tags=["Leadership"])

    async def test_explicit_null_is_ignored_not_written(self, service, mock_repo):
        mock_repo.update_story.return_value = _story()

        await service.update_story(1, InterviewStoryUpdate.model_validate({"situation": None, "strength": 2}))

        mock_repo.update_story.assert_awaited_once_with(1, fields={"strength": 2}, tags=None)

    async def test_not_found(self, service, mock_repo):
        mock_repo.update_story.return_value = None
        assert await service.update_story(999, InterviewStoryUpdate(situation="x")) is None


class TestDeleteAndTags:
    async def test_delete(self, service, mock_repo):
        mock_repo.delete_story.return_value = True
        assert await service.delete_story(1) is True

    async def test_add_tag_returns_story(self, service, mock_repo):
        mock_repo.add_tag.return_value = _story(tags=["Leadership"])
        result = await service.add_tag(1, " Leadership ")
        assert result is not None
        mock_repo.add_tag.assert_awaited_once_with(1, "Leadership")

    async def test_add_tag_story_not_found(self, service, mock_repo):
        mock_repo.add_tag.return_value = None
        assert await service.add_tag(999, "Leadership") is None


class TestAssessStrength:
    async def test_uses_complete_and_logs_llm_call(self, mock_repo):
        llm = _llm('{"score": 4, "reasoning": "Quantify the before state."}')
        svc = InterviewStoryService(AsyncMock(), llm)
        svc._repo = mock_repo
        mock_repo.get_story.return_value = _story()

        with patch("app.features.organizer.interviews.stories.service.create_llm_call", new=AsyncMock()) as log_call:
            result = await svc.assess_strength(1)

        assert result is not None
        assert result.suggested_strength == 4
        assert result.reasoning == "Quantify the before state."
        llm.complete.assert_awaited_once()
        assert log_call.await_args.kwargs["feature"] == "interview_story_strength"

    async def test_strips_markdown_fences(self, mock_repo):
        svc = InterviewStoryService(AsyncMock(), _llm('```json\n{"score": 2, "reasoning": "r"}\n```'))
        svc._repo = mock_repo
        mock_repo.get_story.return_value = _story()

        with patch("app.features.organizer.interviews.stories.service.create_llm_call", new=AsyncMock()):
            result = await svc.assess_strength(1)

        assert result is not None and result.suggested_strength == 2

    async def test_story_not_found_returns_none(self, service, mock_repo):
        mock_repo.get_story.return_value = None
        assert await service.assess_strength(999) is None

    @pytest.mark.parametrize("raw", ["not json", '{"score": 9, "reasoning": "r"}', '{"reasoning": "r"}'])
    async def test_invalid_output_raises(self, mock_repo, raw):
        svc = InterviewStoryService(AsyncMock(), _llm(raw))
        svc._repo = mock_repo
        mock_repo.get_story.return_value = _story()

        with patch("app.features.organizer.interviews.stories.service.create_llm_call", new=AsyncMock()):
            with pytest.raises(StoryAssessmentError):
                await svc.assess_strength(1)

    async def test_llm_failure_raises(self, mock_repo):
        llm = _llm("")
        llm.complete.side_effect = RuntimeError("boom")
        svc = InterviewStoryService(AsyncMock(), llm)
        svc._repo = mock_repo
        mock_repo.get_story.return_value = _story()

        with pytest.raises(StoryAssessmentError):
            await svc.assess_strength(1)
