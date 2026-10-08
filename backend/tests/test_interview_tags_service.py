from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.features.organizer.interviews.tags.schemas import InterviewTagUpdate, normalize_tags
from app.features.organizer.interviews.tags.service import InterviewTagNameTakenError, InterviewTagService
from app.features.organizer.interviews.tags.tables import InterviewTag


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    svc = InterviewTagService(AsyncMock())
    svc._repo = mock_repo
    return svc


class TestNormalizeTags:
    def test_trims_drops_blanks_and_case_insensitive_duplicates(self):
        assert normalize_tags([" Ownership", "", "ownership", "Conflict "]) == ["Ownership", "Conflict"]

    def test_none_passes_through(self):
        assert normalize_tags(None) is None

    def test_rejects_overlong_tag(self):
        with pytest.raises(ValueError):
            normalize_tags(["x" * 101])


class TestGetTags:
    async def test_includes_usage_counts(self, service, mock_repo):
        mock_repo.get_tags_with_usage.return_value = [(InterviewTag(id=1, name="Ownership"), 2, 5)]

        result = await service.get_tags()

        assert [(t.name, t.story_count, t.question_count) for t in result] == [("Ownership", 2, 5)]


class TestRenameTag:
    async def test_renames(self, service, mock_repo):
        mock_repo.get_tag_by_name.return_value = None
        mock_repo.rename_tag.return_value = InterviewTag(id=1, name="Bias for Action")

        result = await service.rename_tag(1, InterviewTagUpdate(name=" Bias for Action "))

        assert result is not None and result.name == "Bias for Action"
        mock_repo.rename_tag.assert_awaited_once_with(1, "Bias for Action")

    async def test_case_only_change_of_same_tag_is_allowed(self, service, mock_repo):
        mock_repo.get_tag_by_name.return_value = InterviewTag(id=1, name="ownership")
        mock_repo.rename_tag.return_value = InterviewTag(id=1, name="Ownership")

        result = await service.rename_tag(1, InterviewTagUpdate(name="Ownership"))

        assert result is not None and result.name == "Ownership"

    async def test_name_taken_by_another_tag(self, service, mock_repo):
        mock_repo.get_tag_by_name.return_value = InterviewTag(id=2, name="Ownership")
        with pytest.raises(InterviewTagNameTakenError):
            await service.rename_tag(1, InterviewTagUpdate(name="ownership"))
        mock_repo.rename_tag.assert_not_awaited()

    async def test_race_on_unique_index_maps_to_name_taken(self, service, mock_repo):
        mock_repo.get_tag_by_name.return_value = None
        mock_repo.rename_tag.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        with pytest.raises(InterviewTagNameTakenError):
            await service.rename_tag(1, InterviewTagUpdate(name="x"))

    async def test_not_found(self, service, mock_repo):
        mock_repo.get_tag_by_name.return_value = None
        mock_repo.rename_tag.return_value = None
        assert await service.rename_tag(999, InterviewTagUpdate(name="x")) is None

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError):
            InterviewTagUpdate(name="   ")


class TestDeleteTag:
    async def test_delete(self, service, mock_repo):
        mock_repo.delete_tag.return_value = True
        assert await service.delete_tag(1) is True

    async def test_delete_not_found(self, service, mock_repo):
        mock_repo.delete_tag.return_value = False
        assert await service.delete_tag(999) is False
