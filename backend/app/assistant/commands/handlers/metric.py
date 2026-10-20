import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.features.metrics.entries.http_errors import ENTRY_ERRORS, to_http_error
from app.assistant.commands.handlers._utils import optional_int, require_int
from app.features.metrics.entries.durations import format_duration, parse_ago
from app.features.metrics.entries.schemas import MetricEntryFilters, MetricEntryRead, MetricLog, MetricStart, MetricStop
from app.features.metrics.entries.service import MetricEntryService

logger = logging.getLogger(__name__)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _tags(arguments: dict[str, Any], extra: str | None = None) -> list[str]:
    """Tags come from the `-t` flag and/or loose words after the series name (comma or space separated)."""
    raw = " ".join(str(v) for v in (arguments.get("tags"), extra) if v)
    return [t for t in raw.replace(",", " ").split() if t]


def _series(arguments: dict[str, Any]) -> str:
    series = (arguments.get("series") or "").strip()
    if not series:
        raise _bad_request("series is required")
    return series


def _source(source: str | None) -> str:
    return "mcp" if source == "mcp" else "telegram"


def _entry_summary(entry: MetricEntryRead) -> dict[str, Any]:
    return {
        "id": entry.id,
        "series": entry.series_name,
        "status": entry.status,
        "started_at": entry.started_at.isoformat(),
        "duration": format_duration(entry.duration_s) if entry.duration_s is not None else None,
        "value": entry.value,
        "tags": entry.tags,
        "stale": entry.is_stale,
    }


async def handle_metric(
    command: str, arguments: dict[str, Any], service: MetricEntryService, source: str | None = None
) -> Any:
    logger.debug("handle_metric: command=%s args_keys=%s", command, list(arguments.keys()))
    entry_source = _source(source)

    try:
        if command == "start":
            data = MetricStart(
                series=_series(arguments),
                tags=_tags(arguments, arguments.get("rest")),
                note=arguments.get("note"),
            )
            result = await service.start(data, entry_source)
            return {"id": result.entry.id, "message": result.message}

        if command == "stop":
            ago_s = None
            if arguments.get("ago"):
                try:
                    ago_s = parse_ago(str(arguments["ago"]))
                except ValueError as exc:
                    raise _bad_request(str(exc))
            series = (arguments.get("series") or "").strip() or None
            result = await service.stop(MetricStop(series=series, ago_s=ago_s), entry_source)
            return {"id": result.entry.id, "message": result.message}

        if command == "log":
            raw_value = arguments.get("value")
            value = None
            if raw_value not in (None, ""):
                try:
                    value = float(str(raw_value).replace(",", "."))
                except ValueError:
                    raise _bad_request(f"value must be a number, got {raw_value!r}")
            data = MetricLog(
                series=_series(arguments), value=value, tags=_tags(arguments), note=arguments.get("note")
            )
            result = await service.log(data, entry_source)
            return {"id": result.entry.id, "message": result.message}

        if command == "open":
            entries = await service.get_open_entries()
            return {"count": len(entries), "entries": [_entry_summary(e) for e in entries]}

        if command == "history":
            limit = optional_int(arguments, "limit", 10)
            filters = MetricEntryFilters(
                series=arguments.get("series"),
                tag=arguments.get("tag"),
                status=None,
                since=None,
                until=None,
                limit=limit + 1,
                offset=optional_int(arguments, "offset", 0),
            )
            entries = await service.get_entries(filters)
            return {
                "count": min(len(entries), limit),
                "has_next": len(entries) > limit,
                "entries": [_entry_summary(e) for e in entries[:limit]],
            }

        if command == "discard":
            entry_id = require_int(arguments, "id")
            entry = await service.discard_entry(entry_id)
            if entry is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Entry {entry_id} not found")
            return {"id": entry.id, "message": f"Entry {entry.id} ({entry.series_name}) discarded"}
    except ValidationError as exc:
        raise _bad_request(exc.errors()[0]["msg"])
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)

    raise _bad_request(f"Unknown command: {command}")
