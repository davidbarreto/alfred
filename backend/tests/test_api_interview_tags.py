from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.interviews.tags.schemas import InterviewTagRead, InterviewTagUsage
from app.features.organizer.interviews.tags.service import InterviewTagNameTakenError

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def client():
    from app.dependencies import get_interview_tag_service
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[get_interview_tag_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


class TestListTags:
    def test_returns_usage_counts(self, client):
        test_client, service = client
        service.get_tags.return_value = [InterviewTagUsage(id=1, name="Ownership", story_count=2, question_count=3)]

        response = test_client.get("/organizer/interview-tags", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == [{"id": 1, "name": "Ownership", "story_count": 2, "question_count": 3}]


class TestRenameTag:
    def test_renames(self, client):
        test_client, service = client
        service.rename_tag.return_value = InterviewTagRead(id=1, name="Bias for Action")

        response = test_client.patch("/organizer/interview-tags/1", json={"name": "Bias for Action"}, headers=AUTH)

        assert response.status_code == 200 and response.json()["name"] == "Bias for Action"

    def test_name_taken_is_409(self, client):
        test_client, service = client
        service.rename_tag.side_effect = InterviewTagNameTakenError("x")
        assert test_client.patch("/organizer/interview-tags/1", json={"name": "x"}, headers=AUTH).status_code == 409

    def test_unknown_tag_is_404(self, client):
        test_client, service = client
        service.rename_tag.return_value = None
        assert test_client.patch("/organizer/interview-tags/9", json={"name": "x"}, headers=AUTH).status_code == 404

    def test_blank_name_is_422(self, client):
        test_client, _ = client
        assert test_client.patch("/organizer/interview-tags/1", json={"name": "  "}, headers=AUTH).status_code == 422


class TestDeleteTag:
    def test_deletes(self, client):
        test_client, service = client
        service.delete_tag.return_value = True
        assert test_client.delete("/organizer/interview-tags/1", headers=AUTH).status_code == 204

    def test_unknown_tag_is_404(self, client):
        test_client, service = client
        service.delete_tag.return_value = False
        assert test_client.delete("/organizer/interview-tags/9", headers=AUTH).status_code == 404
