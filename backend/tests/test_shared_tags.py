from unittest.mock import AsyncMock, MagicMock

from app.features.finance.tags.schemas import TagCreate, TagUpdate
from app.features.organizer.notes.repository import NoteRepository
from app.features.organizer.tasks.repository import TaskRepository
from app.features.study.tags.repository import StudyTagRepository
from app.shared.tags import normalize_tag_name


def _session_without_tags() -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


class TestNormalizeTagName:
    def test_trims_and_lowercases(self):
        assert normalize_tag_name("  Would Return ") == "would return"


class TestFinanceTagSchemas:
    def test_create_lowercases(self):
        assert TagCreate(name=" Travel ").name == "travel"

    def test_update_lowercases_and_keeps_none(self):
        assert TagUpdate(name="Work").name == "work"
        assert TagUpdate().name is None


class TestStudyTags:
    async def test_new_tags_are_lowercase(self):
        session = _session_without_tags()
        tags = await StudyTagRepository(session).resolve_tags(["Graphs", " DP "])
        assert [t.name for t in tags] == ["graphs", "dp"]


class TestOrganizerTags:
    async def test_task_tags_are_lowercase(self):
        session = _session_without_tags()
        tags = await TaskRepository(session)._resolve_tags(["Work"], "notion")
        assert [t.name for t in tags] == ["work"]

    async def test_note_tags_are_lowercase(self):
        session = _session_without_tags()
        tags = await NoteRepository(session)._resolve_tags(["Ideas"], "notion")
        assert [t.name for t in tags] == ["ideas"]
