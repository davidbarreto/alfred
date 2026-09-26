from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.interviews.candidate_questions.repository import InterviewCandidateQuestionRepository
from app.features.organizer.interviews.prep_questions.repository import InterviewPrepQuestionRepository
from app.features.organizer.interviews.stories.repository import InterviewStoryRepository


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.scalar.return_value = MagicMock(id=1, tags=[])
    session.get.return_value = MagicMock()
    session.execute.return_value = MagicMock(rowcount=1)
    return session


class TestMutationsCommit:
    """Every mutation must commit: get_session() never commits, so a flush-only write is rolled back."""

    @pytest.mark.parametrize("call", [
        lambda r: r.create_story("s", "t", "a", "r", 3, ["x"]),
        lambda r: r.update_story(1, {"strength": 4}, None),
        lambda r: r.delete_story(1),
        lambda r: r.add_tag(1, "new"),
        lambda r: r.remove_tag(1, "x"),
    ])
    async def test_story_repository(self, call):
        session = _session()
        await call(InterviewStoryRepository(session))
        session.commit.assert_awaited()

    @pytest.mark.parametrize("call", [
        lambda r: r.create_question("q"),
        lambda r: r.update_question(1, "q2"),
        lambda r: r.delete_question(1),
        lambda r: r.link_story(1, 1, 4),
        lambda r: r.unlink_story(1, 1),
    ])
    async def test_prep_question_repository(self, call):
        session = _session()
        await call(InterviewPrepQuestionRepository(session))
        session.commit.assert_awaited()

    @pytest.mark.parametrize("call", [
        lambda r: r.create_question("q", "Tech"),
        lambda r: r.update_question(1, {"category": "Growth"}),
        lambda r: r.delete_question(1),
    ])
    async def test_candidate_question_repository(self, call):
        session = _session()
        await call(InterviewCandidateQuestionRepository(session))
        session.commit.assert_awaited()
