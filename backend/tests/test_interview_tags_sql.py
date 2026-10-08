"""Compile the tag queries against the real Postgres dialect (mocked sessions can't catch SQL bugs)."""
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from app.features.organizer.interviews.prep_questions.repository import InterviewPrepQuestionRepository
from app.features.organizer.interviews.stories.repository import InterviewStoryRepository
from app.features.organizer.interviews.tags.repository import InterviewTagRepository


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).lower()


def _session() -> AsyncMock:
    session = AsyncMock()
    session.scalars.return_value = MagicMock(all=lambda: [])
    session.execute.return_value = MagicMock(all=lambda: [])
    return session


class TestTagQueries:
    async def test_story_filter_matches_tag_case_insensitively(self):
        session = _session()
        await InterviewStoryRepository(session).get_stories_by_tag("Ownership")
        sql = _sql(session.scalars.call_args.args[0])
        assert "interview_story_tag_links" in sql and "lower(organizer.interview_tags.name) = 'ownership'" in sql

    async def test_question_filter_matches_tag_case_insensitively(self):
        session = _session()
        await InterviewPrepQuestionRepository(session).get_questions(tag="Ownership")
        sql = _sql(session.scalars.call_args.args[0])
        assert "interview_question_tag_links" in sql and "lower(organizer.interview_tags.name) = 'ownership'" in sql

    async def test_question_without_tag_has_no_tag_join(self):
        session = _session()
        await InterviewPrepQuestionRepository(session).get_questions()
        assert "interview_question_tag_links" not in _sql(session.scalars.call_args.args[0])

    async def test_usage_counts_query_compiles(self):
        session = _session()
        await InterviewTagRepository(session).get_tags_with_usage()
        sql = _sql(session.execute.call_args.args[0])
        assert "interview_story_tag_links" in sql and "interview_question_tag_links" in sql and "coalesce" in sql
