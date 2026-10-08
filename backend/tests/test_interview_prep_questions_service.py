from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.features.organizer.interviews.prep_questions.schemas import (
    InterviewPrepQuestionCreate,
    InterviewPrepQuestionUpdate,
)
from app.features.organizer.interviews.prep_questions.service import InterviewPrepQuestionService
from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion, InterviewPrepQuestionStory
from app.features.organizer.interviews.stories.tables import InterviewStory
from app.features.organizer.interviews.tags.tables import InterviewTag

_NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def _question(id=1, text="Tell me about a difficult decision", links=(), tags=()) -> InterviewPrepQuestion:
    return InterviewPrepQuestion(
        id=id, text=text, created_at=_NOW, updated_at=_NOW, story_links=list(links),
        tags=[InterviewTag(id=i + 1, name=t) for i, t in enumerate(tags)],
    )


def _link(story_id: int, fit_score: int, strength: int = 3) -> InterviewPrepQuestionStory:
    story = InterviewStory(
        id=story_id, situation=f"s{story_id}", task="t", action="a", result="r",
        strength=strength, tags=[], created_at=_NOW, updated_at=_NOW,
    )
    return InterviewPrepQuestionStory(question_id=1, story_id=story_id, fit_score=fit_score, story=story)


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    svc = InterviewPrepQuestionService(AsyncMock())
    svc._repo = mock_repo
    return svc


class TestCrud:
    async def test_create_returns_read_model(self, service, mock_repo):
        mock_repo.create_question.return_value = _question()

        result = await service.create_question(InterviewPrepQuestionCreate(text="Tell me about a difficult decision"))

        assert result.id == 1
        assert result.created_at == _NOW
        mock_repo.create_question.assert_awaited_once_with(text="Tell me about a difficult decision", tags=[])

    async def test_create_passes_normalized_tags_and_returns_them(self, service, mock_repo):
        mock_repo.create_question.return_value = _question(tags=["Ownership"])

        result = await service.create_question(
            InterviewPrepQuestionCreate(text="q", tags=[" Ownership ", "ownership", ""])
        )

        assert [t.name for t in result.tags] == ["Ownership"]
        mock_repo.create_question.assert_awaited_once_with(text="q", tags=["Ownership"])

    async def test_update_passes_tags_through_only_when_set(self, service, mock_repo):
        mock_repo.update_question.return_value = _question(tags=["Conflict"])

        await service.update_question(1, InterviewPrepQuestionUpdate(tags=["Conflict"]))
        mock_repo.update_question.assert_awaited_with(question_id=1, text=None, tags=["Conflict"])

        await service.update_question(1, InterviewPrepQuestionUpdate(text="x"))
        mock_repo.update_question.assert_awaited_with(question_id=1, text="x", tags=None)

    async def test_update(self, service, mock_repo):
        mock_repo.update_question.return_value = _question(text="Updated")
        result = await service.update_question(1, InterviewPrepQuestionUpdate(text="Updated"))
        assert result is not None and result.text == "Updated"

    async def test_update_not_found(self, service, mock_repo):
        mock_repo.update_question.return_value = None
        assert await service.update_question(999, InterviewPrepQuestionUpdate(text="x")) is None


class TestListStoryCount:
    async def test_list_includes_linked_story_count_defaulting_to_zero(self, service, mock_repo):
        mock_repo.get_questions.return_value = [_question(id=1), _question(id=2)]
        mock_repo.get_story_counts.return_value = {1: 3}

        result = await service.get_questions()

        assert [(q.id, q.story_count) for q in result] == [(1, 3), (2, 0)]
        mock_repo.get_story_counts.assert_awaited_once_with([1, 2])


class TestTags:
    async def test_list_filters_by_tag(self, service, mock_repo):
        mock_repo.get_questions.return_value = [_question(tags=["Ownership"])]
        mock_repo.get_story_counts.return_value = {}

        result = await service.get_questions(tag="Ownership", limit=10, offset=5)

        mock_repo.get_questions.assert_awaited_once_with(tag="Ownership", limit=10, offset=5)
        assert [t.name for t in result[0].tags] == ["Ownership"]

    async def test_add_tag_strips_and_returns_question(self, service, mock_repo):
        mock_repo.add_tag.return_value = _question(tags=["Ownership"])

        result = await service.add_tag(1, " Ownership ")

        mock_repo.add_tag.assert_awaited_once_with(1, "Ownership")
        assert result is not None and [t.name for t in result.tags] == ["Ownership"]

    async def test_add_tag_question_not_found(self, service, mock_repo):
        mock_repo.add_tag.return_value = None
        assert await service.add_tag(999, "x") is None

    async def test_remove_tag(self, service, mock_repo):
        mock_repo.remove_tag.return_value = True
        assert await service.remove_tag(1, "x") is True
        mock_repo.remove_tag.return_value = False
        assert await service.remove_tag(1, "missing") is False

    async def test_detail_includes_question_tags(self, service, mock_repo):
        mock_repo.get_question_with_links.return_value = _question(tags=["A", "B"])
        result = await service.get_question_with_stories(1)
        assert result is not None and [t.name for t in result.tags] == ["A", "B"]


class TestQuestionWithStories:
    async def test_stories_carry_fit_score_sorted_best_first(self, service, mock_repo):
        mock_repo.get_question_with_links.return_value = _question(
            links=[_link(10, fit_score=2), _link(11, fit_score=5), _link(12, fit_score=5, strength=4)]
        )

        result = await service.get_question_with_stories(1)

        assert result is not None
        assert [(s.id, s.fit_score) for s in result.stories] == [(12, 5), (11, 5), (10, 2)]

    async def test_not_found(self, service, mock_repo):
        mock_repo.get_question_with_links.return_value = None
        assert await service.get_question_with_stories(999) is None


class TestLinkStory:
    async def test_links_when_both_exist(self, service, mock_repo):
        mock_repo.get_question.return_value = _question()
        mock_repo.story_exists.return_value = True
        mock_repo.link_story.return_value = InterviewPrepQuestionStory(question_id=1, story_id=2, fit_score=4)

        result = await service.link_story(1, 2, 4)

        assert result is not None and result.fit_score == 4
        mock_repo.link_story.assert_awaited_once_with(1, 2, 4)

    async def test_missing_question(self, service, mock_repo):
        mock_repo.get_question.return_value = None
        mock_repo.story_exists.return_value = True
        assert await service.link_story(999, 2, 3) is None
        mock_repo.link_story.assert_not_awaited()

    async def test_missing_story_does_not_hit_fk_error(self, service, mock_repo):
        mock_repo.get_question.return_value = _question()
        mock_repo.story_exists.return_value = False
        assert await service.link_story(1, 999, 3) is None
        mock_repo.link_story.assert_not_awaited()


class TestUnlinkStory:
    async def test_unlink(self, service, mock_repo):
        mock_repo.unlink_story.return_value = True
        assert await service.unlink_story(1, 1) is True

    async def test_unlink_not_found(self, service, mock_repo):
        mock_repo.unlink_story.return_value = False
        assert await service.unlink_story(999, 999) is False
