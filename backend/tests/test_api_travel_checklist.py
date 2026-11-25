from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.travel.checklist.schemas import (
    ChecklistGenerated,
    ChecklistItemRead,
    ChecklistItemWrite,
    ChecklistTemplateRead,
)
from app.features.travel.errors import TravelNotFoundError

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def api():
    import app.dependencies as deps
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[deps.get_checklist_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


def test_get_template(api):
    client, service = api
    service.get_template.return_value = ChecklistTemplateRead(
        items=[ChecklistItemRead(anchor="start", name="currency", title="currency", offset_days=-14)]
    )
    assert client.get("/travel/checklist-template", headers=AUTH).json() == {
        "items": [{"anchor": "start", "name": "currency", "title": "currency", "offset_days": -14}]
    }


def test_put_replaces_the_template(api):
    client, service = api
    service.replace_template.return_value = ChecklistTemplateRead(
        items=[ChecklistItemRead(anchor="end", name="x", title="x", offset_days=3)]
    )
    resp = client.put("/travel/checklist-template", headers=AUTH, json={"items": [{"anchor": "end", "name": "x", "offset_days": 3}]})
    assert resp.status_code == 200 and resp.json()["items"][0]["name"] == "x"
    service.replace_template.assert_awaited_once_with([ChecklistItemWrite(anchor="end", name="x", offset_days=3)])


@pytest.mark.parametrize("items", [
    [{"anchor": "end", "name": "x", "offset_days": 3}, {"anchor": "start", "name": "x", "offset_days": -3}],
    [{"anchor": "mid", "name": "x", "offset_days": 3}],
    [{"anchor": "end", "name": "Bad Name", "offset_days": 3}],
])
def test_put_invalid_or_duplicate_is_422(api, items):
    client, service = api
    assert client.put("/travel/checklist-template", headers=AUTH, json={"items": items}).status_code == 422
    service.replace_template.assert_not_awaited()


def test_generate(api):
    client, service = api
    service.generate.return_value = ChecklistGenerated(created=["a (T)"], skipped=[])
    assert client.post("/travel/trips/1/checklist", headers=AUTH).json() == {"created": ["a (T)"], "skipped": []}
    service.generate.side_effect = TravelNotFoundError("Trip 1 not found")
    assert client.post("/travel/trips/1/checklist", headers=AUTH).status_code == 404
