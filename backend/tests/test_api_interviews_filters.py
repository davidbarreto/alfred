from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def client():
    from app.main import app
    from app.dependencies import (
        get_interview_process_service,
        get_interview_stage_service,
        get_interview_insight_service,
    )

    app.dependency_overrides[get_interview_process_service] = lambda: AsyncMock(get_processes=AsyncMock(return_value=[]))
    app.dependency_overrides[get_interview_stage_service] = lambda: AsyncMock(get_stages=AsyncMock(return_value=[]))
    app.dependency_overrides[get_interview_insight_service] = lambda: AsyncMock(get_insights_history=AsyncMock(return_value=[]))
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListFiltersDependencyResolves:
    """Regression test: these Filters classes previously combined `from __future__ import
    annotations` with `Annotated[X, Query(...)] = default` parameters, which made FastAPI's
    Pydantic TypeAdapter fail to build at request time (PydanticUserError: TypeAdapter is not
    fully defined). Mocked service-layer tests never exercise real route dependency resolution,
    so this only ever surfaced as a live 500. Hitting the actual routes here would have caught it.
    """

    def test_list_processes(self, client):
        response = client.get("/organizer/interview-processes?limit=5", headers=AUTH)
        assert response.status_code == 200

    def test_list_stages(self, client):
        response = client.get("/organizer/interview-stages?limit=5", headers=AUTH)
        assert response.status_code == 200

    def test_list_insights(self, client):
        response = client.get("/organizer/interview-insights?limit=5", headers=AUTH)
        assert response.status_code == 200
