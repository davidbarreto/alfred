from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.metric import handle_metric
from app.features.metrics.entries.schemas import MetricActionResult, MetricEntryRead
from app.features.metrics.entries.service import (
    MetricAmbiguousStopError,
    MetricKindMismatchError,
    MetricNothingRunningError,
)

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def _read(id=1, status="open", duration_s=None) -> MetricEntryRead:
    return MetricEntryRead(
        id=id, series_id=1, series_name="commute-work", series_kind="duration", started_at=NOW, ended_at=None,
        duration_s=duration_s, value=None, status=status, source="telegram", start_lat=None, start_lon=None,
        start_accuracy_m=None, end_lat=None, end_lon=None, end_accuracy_m=None, context=None, note=None,
        tags=["bus"], created_at=NOW, updated_at=NOW,
    )


class TestStart:
    async def test_tags_come_from_loose_words_and_the_flag(self):
        service = AsyncMock()
        service.start.return_value = MetricActionResult(message="Started", entry=_read())

        await handle_metric("start", {"series": "commute-work", "rest": "bus, metro", "tags": "rain"}, service)

        data, source = service.start.await_args.args
        assert data.series == "commute-work" and data.tags == ["rain", "bus", "metro"]
        assert source == "telegram"

    async def test_mcp_source_is_preserved(self):
        service = AsyncMock()
        service.start.return_value = MetricActionResult(message="Started", entry=_read())
        await handle_metric("start", {"series": "x"}, service, source="mcp")
        assert service.start.await_args.args[1] == "mcp"

    async def test_missing_series_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("start", {}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_invalid_series_name_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("start", {"series": "bad/name"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_kind_mismatch_is_409(self):
        service = AsyncMock()
        service.start.side_effect = MetricKindMismatchError("sleep", "value", "duration")
        with pytest.raises(HTTPException) as exc:
            await handle_metric("start", {"series": "sleep"}, service)
        assert exc.value.status_code == 409


class TestStop:
    async def test_parses_ago(self):
        service = AsyncMock()
        service.stop.return_value = MetricActionResult(message="Stopped", entry=_read(status="closed", duration_s=60))
        await handle_metric("stop", {"ago": "1h30m"}, service)
        data = service.stop.await_args.args[0]
        assert data.ago_s == 5400 and data.series is None

    async def test_bad_ago_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("stop", {"ago": "soon"}, AsyncMock())
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("error", [MetricNothingRunningError(None), MetricAmbiguousStopError(["a", "b"])])
    async def test_domain_errors_are_409(self, error):
        service = AsyncMock()
        service.stop.side_effect = error
        with pytest.raises(HTTPException) as exc:
            await handle_metric("stop", {}, service)
        assert exc.value.status_code == 409


class TestLog:
    async def test_numeric_value_with_decimal_comma(self):
        service = AsyncMock()
        service.log.return_value = MetricActionResult(message="Logged", entry=_read())
        await handle_metric("log", {"series": "sleep", "value": "7,5"}, service)
        assert service.log.await_args.args[0].value == 7.5

    async def test_log_passes_the_unit_flag(self):
        service = AsyncMock()
        service.log.return_value = MetricActionResult(message="Logged", entry=_read())
        await handle_metric("log", {"series": "weight", "value": "80", "unit": "kg"}, service)
        assert service.log.await_args.args[0].unit == "kg"

    async def test_no_value_is_a_count(self):
        service = AsyncMock()
        service.log.return_value = MetricActionResult(message="Logged", entry=_read())
        await handle_metric("log", {"series": "coffee"}, service)
        assert service.log.await_args.args[0].value is None

    async def test_non_numeric_value_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("log", {"series": "sleep", "value": "lots"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_nan_value_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("log", {"series": "sleep", "value": "nan"}, AsyncMock())
        assert exc.value.status_code == 400


class TestReads:
    async def test_open_lists_summaries(self):
        service = AsyncMock()
        service.get_open_entries.return_value = [_read(id=3)]
        result = await handle_metric("open", {}, service)
        assert result["count"] == 1 and result["entries"][0]["id"] == 3

    async def test_history_uses_limit_plus_one_for_has_next(self):
        service = AsyncMock()
        service.get_entries.return_value = [_read(id=i) for i in range(3)]
        result = await handle_metric("history", {"series": "commute-work", "limit": "2"}, service)
        assert service.get_entries.await_args.args[0].limit == 3
        assert result["count"] == 2 and result["has_next"] is True

    async def test_discard_unknown_is_404(self):
        service = AsyncMock()
        service.discard_entry.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_metric("discard", {"id": "9"}, service)
        assert exc.value.status_code == 404

    async def test_discard_requires_integer_id(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("discard", {"id": "abc"}, AsyncMock())
        assert exc.value.status_code == 400

    async def test_unknown_command_is_400(self):
        with pytest.raises(HTTPException) as exc:
            await handle_metric("nope", {}, AsyncMock())
        assert exc.value.status_code == 400
