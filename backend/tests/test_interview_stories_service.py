import pytest
from unittest.mock import AsyncMock, MagicMock

from app.features.organizer.interviews.stories.service import InterviewStoryService
from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryUpdate
from app.features.organizer.interviews.stories.tables import InterviewStory, InterviewStoryTag


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    service = InterviewStoryService(AsyncMock())
    service._repo = mock_repo
    return service


class TestCreateStory:
    async def test_create_story_with_tags(self, service, mock_repo):
        story = InterviewStory(
            id=1,
            situation="Faced a deadline pressure",
            task="Complete project on time",
            action="Prioritized tasks",
            result="Delivered on time",
            strength=4,
        )
        mock_repo.create_story.return_value = story
        mock_repo.set_tags.return_value = None

        data = InterviewStoryCreate(
            situation="Faced a deadline pressure",
            task="Complete project on time",
            action="Prioritized tasks",
            result="Delivered on time",
            strength=4,
            tags=["Leadership", "Problem-Solving"],
        )

        result = await service.create_story(data)

        assert result.id == 1
        assert result.strength == 4
        mock_repo.create_story.assert_called_once()
        mock_repo.set_tags.assert_called_once_with(1, ["Leadership", "Problem-Solving"])

    async def test_create_story_without_tags(self, service, mock_repo):
        story = InterviewStory(
            id=1,
            situation="Situation",
            task="Task",
            action="Action",
            result="Result",
            strength=3,
        )
        mock_repo.create_story.return_value = story

        data = InterviewStoryCreate(
            situation="Situation",
            task="Task",
            action="Action",
            result="Result",
            strength=3,
            tags=[],
        )

        result = await service.create_story(data)

        assert result.id == 1
        mock_repo.set_tags.assert_not_called()


class TestUpdateStory:
    async def test_update_story(self, service, mock_repo):
        updated_story = InterviewStory(
            id=1,
            situation="Updated situation",
            task="Task",
            action="Action",
            result="Result",
            strength=5,
        )
        mock_repo.update_story.return_value = updated_story

        data = InterviewStoryUpdate(
            situation="Updated situation",
            strength=5,
            tags=["Leadership"],
        )

        result = await service.update_story(1, data)

        assert result.strength == 5
        mock_repo.set_tags.assert_called_once_with(1, ["Leadership"])

    async def test_update_story_not_found(self, service, mock_repo):
        mock_repo.update_story.return_value = None

        data = InterviewStoryUpdate(situation="Updated")

        result = await service.update_story(999, data)

        assert result is None


class TestDeleteStory:
    async def test_delete_story(self, service, mock_repo):
        mock_repo.delete_story.return_value = True

        result = await service.delete_story(1)

        assert result is True
        mock_repo.delete_story.assert_called_once_with(1)

    async def test_delete_story_not_found(self, service, mock_repo):
        mock_repo.delete_story.return_value = False

        result = await service.delete_story(999)

        assert result is False


class TestTags:
    async def test_add_tag(self, service, mock_repo):
        tag = InterviewStoryTag(id=1, story_id=1, tag="Leadership")
        mock_repo.add_tag.return_value = tag

        result = await service.add_tag(1, "Leadership")

        assert result is True

    async def test_add_tag_story_not_found(self, service, mock_repo):
        mock_repo.add_tag.return_value = None

        result = await service.add_tag(999, "Leadership")

        assert result is False

    async def test_remove_tag(self, service, mock_repo):
        mock_repo.remove_tag.return_value = True

        result = await service.remove_tag(1, "Leadership")

        assert result is True

    async def test_get_all_tags(self, service, mock_repo):
        mock_repo.get_all_tags.return_value = ["Leadership", "Teamwork", "Problem-Solving"]

        result = await service.get_all_tags()

        assert result == ["Leadership", "Teamwork", "Problem-Solving"]
