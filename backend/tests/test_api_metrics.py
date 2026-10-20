from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.metrics.entries.schemas import MetricActionResult, MetricEntryRead
from app.features.metrics.entries.service import (
    MetricInvalidEntryError,
    MetricNothingRunningError,
    MetricSeriesNotFoundError,
    MetricStaleEntryError,
)
from app.features.metrics.series.schemas import MetricSeriesRead, MetricSeriesSummary
from app.features.metrics.series.service import (
    MetricSeriesMergeError,
    MetricSeriesNameTakenError,
    MetricSeriesNotEmptyError,
)
from app.features.metrics.tags.schemas import MetricTagRead, MetricTagUsage
from app.features.metrics.tags.service import MetricTagInUseError, MetricTagNameTakenError

AUTH = {"Authorization": "Bearer test-api-token"}
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def _entry(id=1) -> MetricEntryRead:
    return MetricEntryRead(
        id=id, series_id=1, series_name="commute-work", series_kind="duration", started_at=NOW, ended_at=None,
        duration_s=None, value=None, status="open", source="shortcut", start_lat=None, start_lon=None,
        start_accuracy_m=None, end_lat=None, end_lon=None, end_accuracy_m=None, context=None, note=None,
        tags=["bus"], created_at=NOW, updated_at=NOW,
    )


def _series(name="commute-work") -> MetricSeriesRead:
    return MetricSeriesRead(
        id=1, name=name, kind="duration", unit=None, description=None, is_archived=False, created_at=NOW, updated_at=NOW
    )


@pytest.fixture
def entries():
    from app.dependencies import get_metric_entry_service
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[get_metric_entry_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


@pytest.fixture
def series():
    from app.dependencies import get_metric_series_service
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[get_metric_series_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


@pytest.fixture
def tags():
    from app.dependencies import get_metric_tag_service
    from app.main import app

    service = AsyncMock()
    app.dependency_overrides[get_metric_tag_service] = lambda: service
    yield TestClient(app), service
    app.dependency_overrides.clear()


class TestAuth:
    @pytest.mark.parametrize("path", ["/metrics/series", "/metrics/entries", "/metrics/entries/open", "/metrics/tags"])
    def test_requires_token(self, path):
        from app.main import app

        assert TestClient(app).get(path).status_code in (401, 403)


class TestQuick:
    def test_start(self, entries):
        client, service = entries
        service.start.return_value = MetricActionResult(message="Started commute-work [bus]", entry=_entry())

        response = client.post(
            "/metrics/quick/start",
            json={"series": "Commute Work", "tags": ["bus"], "lat": 41.2, "lon": -8.6, "accuracy_m": 15},
            headers={**AUTH, "X-Alfred-Client": "shortcut"},
        )

        assert response.status_code == 200 and response.json()["message"] == "Started commute-work [bus]"
        data, source = service.start.await_args.args
        assert data.series == "commute-work" and (data.lat, data.lon) == (41.2, -8.6) and source == "shortcut"

    def test_source_defaults_to_mcp_and_web_is_portal(self, entries):
        client, service = entries
        service.log.return_value = MetricActionResult(message="Logged", entry=_entry())
        client.post("/metrics/quick/log", json={"series": "coffee"}, headers=AUTH)
        client.post("/metrics/quick/log", json={"series": "coffee"}, headers={**AUTH, "X-Alfred-Client": "web"})
        assert [c.args[1] for c in service.log.await_args_list] == ["mcp", "portal"]

    def test_stop_nothing_running_is_409(self, entries):
        client, service = entries
        service.stop.side_effect = MetricNothingRunningError("commute-work")
        assert client.post("/metrics/quick/stop", json={"series": "commute-work"}, headers=AUTH).status_code == 409

    def test_stop_stale_is_409(self, entries):
        client, service = entries
        service.stop.side_effect = MetricStaleEntryError(4)
        assert client.post("/metrics/quick/stop", json={}, headers=AUTH).status_code == 409

    def test_lat_without_lon_is_422(self, entries):
        client, _ = entries
        assert client.post("/metrics/quick/start", json={"series": "x", "lat": 41.0}, headers=AUTH).status_code == 422

    def test_out_of_range_coordinates_are_422(self, entries):
        client, _ = entries
        body = {"series": "x", "lat": 91, "lon": 0}
        assert client.post("/metrics/quick/start", json=body, headers=AUTH).status_code == 422

    def test_negative_ago_is_422(self, entries):
        client, _ = entries
        assert client.post("/metrics/quick/stop", json={"ago_s": -1}, headers=AUTH).status_code == 422


class TestEntries:
    def test_list_passes_filters(self, entries):
        client, service = entries
        service.get_entries.return_value = [_entry()]

        response = client.get("/metrics/entries?series=commute-work&tag=bus&status=closed&limit=5&offset=10", headers=AUTH)

        assert response.status_code == 200 and response.json()[0]["tags"] == ["bus"]
        filters = service.get_entries.await_args.args[0]
        assert (filters.series, filters.tag, filters.status, filters.limit, filters.offset) == (
            "commute-work", "bus", "closed", 5, 10
        )

    def test_list_defaults(self, entries):
        client, service = entries
        service.get_entries.return_value = []
        client.get("/metrics/entries", headers=AUTH)
        filters = service.get_entries.await_args.args[0]
        assert (filters.limit, filters.offset, filters.status) == (50, 0, None)

    def test_invalid_status_filter_is_422(self, entries):
        client, _ = entries
        assert client.get("/metrics/entries?status=weird", headers=AUTH).status_code == 422

    def test_open_is_not_shadowed_by_the_id_route(self, entries):
        client, service = entries
        service.get_open_entries.return_value = [_entry()]
        assert client.get("/metrics/entries/open", headers=AUTH).status_code == 200

    def test_get_unknown_is_404(self, entries):
        client, service = entries
        service.get_entry.return_value = None
        assert client.get("/metrics/entries/9", headers=AUTH).status_code == 404

    def test_create(self, entries):
        client, service = entries
        service.create_entry.return_value = _entry()
        body = {"series": "commute-work", "started_at": "2026-10-21T08:00:00Z", "ended_at": "2026-10-21T08:34:00Z"}
        assert client.post("/metrics/entries", json=body, headers=AUTH).status_code == 201

    def test_create_unknown_series_is_404(self, entries):
        client, service = entries
        service.create_entry.side_effect = MetricSeriesNotFoundError("ghost")
        body = {"series": "ghost", "started_at": "2026-10-21T08:00:00Z"}
        assert client.post("/metrics/entries", json=body, headers=AUTH).status_code == 404

    def test_create_inconsistent_is_422(self, entries):
        client, service = entries
        service.create_entry.side_effect = MetricInvalidEntryError("A duration entry needs an end time")
        body = {"series": "commute-work", "started_at": "2026-10-21T08:00:00Z"}
        assert client.post("/metrics/entries", json=body, headers=AUTH).status_code == 422

    def test_patch_unknown_is_404(self, entries):
        client, service = entries
        service.update_entry.return_value = None
        assert client.patch("/metrics/entries/9", json={"note": "x"}, headers=AUTH).status_code == 404

    def test_patch_invalid_is_422(self, entries):
        client, service = entries
        service.update_entry.side_effect = MetricInvalidEntryError("The end time is before the start time")
        assert client.patch("/metrics/entries/1", json={"note": "x"}, headers=AUTH).status_code == 422

    def test_discard(self, entries):
        client, service = entries
        service.discard_entry.return_value = _entry()
        assert client.post("/metrics/entries/1/discard", headers=AUTH).status_code == 200

    def test_discard_unknown_is_404(self, entries):
        client, service = entries
        service.discard_entry.return_value = None
        assert client.post("/metrics/entries/9/discard", headers=AUTH).status_code == 404


class TestSeries:
    def test_list(self, series):
        client, service = series
        service.get_all_series.return_value = [MetricSeriesSummary(**_series().model_dump(), entry_count=7)]
        response = client.get("/metrics/series", headers=AUTH)
        assert response.status_code == 200 and response.json()[0]["entry_count"] == 7
        service.get_all_series.assert_awaited_once_with(include_archived=False)

    def test_create_normalises_name(self, series):
        client, service = series
        service.create_series.return_value = _series()
        response = client.post("/metrics/series", json={"name": "Commute Work", "kind": "duration"}, headers=AUTH)
        assert response.status_code == 201
        assert service.create_series.await_args.args[0].name == "commute-work"

    def test_create_duplicate_is_409(self, series):
        client, service = series
        service.create_series.side_effect = MetricSeriesNameTakenError("x")
        assert client.post("/metrics/series", json={"name": "x", "kind": "count"}, headers=AUTH).status_code == 409

    def test_create_invalid_kind_is_422(self, series):
        client, _ = series
        assert client.post("/metrics/series", json={"name": "x", "kind": "weird"}, headers=AUTH).status_code == 422

    def test_get_unknown_is_404(self, series):
        client, service = series
        service.get_series.return_value = None
        assert client.get("/metrics/series/ghost", headers=AUTH).status_code == 404

    def test_archive(self, series):
        client, service = series
        service.update_series.return_value = _series()
        assert client.patch("/metrics/series/commute-work", json={"is_archived": True}, headers=AUTH).status_code == 200

    def test_merge_conflict_is_409(self, series):
        client, service = series
        service.merge_series.side_effect = MetricSeriesMergeError("different kinds")
        assert client.post("/metrics/series/a/merge", json={"into": "b"}, headers=AUTH).status_code == 409

    def test_delete_with_entries_is_409_and_mentions_the_count(self, series):
        client, service = series
        service.delete_series.side_effect = MetricSeriesNotEmptyError(12)
        response = client.delete("/metrics/series/commute-work", headers=AUTH)
        assert response.status_code == 409 and "12" in response.json()["detail"]

    def test_delete_empty(self, series):
        client, service = series
        service.delete_series.return_value = True
        assert client.delete("/metrics/series/typo", headers=AUTH).status_code == 204


class TestTags:
    def test_list(self, tags):
        client, service = tags
        service.get_tags.return_value = [MetricTagUsage(id=1, name="bus", entry_count=4)]
        assert client.get("/metrics/tags", headers=AUTH).json() == [{"id": 1, "name": "bus", "entry_count": 4}]

    def test_rename_clash_is_409(self, tags):
        client, service = tags
        service.rename_tag.side_effect = MetricTagNameTakenError("x")
        assert client.patch("/metrics/tags/1", json={"name": "x"}, headers=AUTH).status_code == 409

    def test_rename(self, tags):
        client, service = tags
        service.rename_tag.return_value = MetricTagRead(id=1, name="Bus")
        assert client.patch("/metrics/tags/1", json={"name": "Bus"}, headers=AUTH).json()["name"] == "Bus"

    def test_delete_in_use_is_409(self, tags):
        client, service = tags
        service.delete_tag.side_effect = MetricTagInUseError(3)
        assert client.delete("/metrics/tags/1", headers=AUTH).status_code == 409

    def test_delete_unknown_is_404(self, tags):
        client, service = tags
        service.delete_tag.return_value = False
        assert client.delete("/metrics/tags/9", headers=AUTH).status_code == 404
