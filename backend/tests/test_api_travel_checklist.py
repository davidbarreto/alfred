from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.travel.checklist.schemas import ChecklistGenerated, ChecklistItemRead
from app.features.travel.errors import TravelConflictError, TravelNotFoundError

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
    service.get_template.return_value = [ChecklistItemRead(anchor="start", name="currency", title="currency", offset_days=-14)]
    assert client.get("/travel/checklist-template", headers=AUTH).json() == [
        {"anchor": "start", "name": "currency", "title": "currency", "offset_days": -14}
    ]


def test_put_item(api):
    client, service = api
    service.put_item.return_value = ChecklistItemRead(anchor="end", name="x", title="x", offset_days=3)
    resp = client.put("/travel/checklist-template/end/x", headers=AUTH, json={"offset_days": 3})
    assert resp.status_code == 200
    service.put_item.assert_awaited_once_with("end", "x", 3)


def test_put_duplicate_is_409_and_invalid_is_422(api):
    client, service = api
    service.put_item.side_effect = TravelConflictError("exists")
    assert client.put("/travel/checklist-template/end/x", headers=AUTH, json={"offset_days": 3}).status_code == 409
    service.put_item.side_effect = ValueError("bad anchor")
    assert client.put("/travel/checklist-template/mid/x", headers=AUTH, json={"offset_days": 3}).status_code == 422


def test_delete_item(api):
    client, service = api
    service.delete_item.return_value = True
    assert client.delete("/travel/checklist-template/start/x", headers=AUTH).status_code == 204
    service.delete_item.return_value = False
    assert client.delete("/travel/checklist-template/start/x", headers=AUTH).status_code == 404


def test_generate(api):
    client, service = api
    service.generate.return_value = ChecklistGenerated(created=["a (T)"], skipped=[])
    assert client.post("/travel/trips/1/checklist", headers=AUTH).json() == {"created": ["a (T)"], "skipped": []}
    service.generate.side_effect = TravelNotFoundError("Trip 1 not found")
    assert client.post("/travel/trips/1/checklist", headers=AUTH).status_code == 404
