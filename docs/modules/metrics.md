# Metrics module

Personal measurement log (`metrics` schema). Design and phases: `docs/plans/metrics.md`.

## Data model

- **Series** (`metrics.series`) = the thing measured (`commute-work`), with a kind: `duration` (start/stop), `value` (one number), `count` (one event). Names are lowercase slugs. Created automatically on first `/mstart` or `/mlog`.
- **Entries** (`metrics.entries`): `started_at`, `ended_at`, `value`, `status` (`open`/`closed`/`discarded`), `source` (`telegram`/`shortcut`/`portal`/`mcp`), start/stop coordinates, `context` JSON (`{start: weather, end: weather}`). Duration is **derived** (`ended_at - started_at`), never stored. Weekday/hour are derived at query time in the configured timezone.
- **Tags** (`metrics.tags` + `entries_tags`, ORM class `MetricTag`) are the options compared inside a series (`bus`, `metro`).
- **No cascades**: every FK is `RESTRICT`. Entries are discarded, series archived or merged; deleting a series with entries is a 409.

## Start / stop rules

`stop` closes the latest open entry; a new `start` discards a still-open one; open entries older than 6 h are stale, and a stop that would make an entry last over 6 h is a 409 (backdate with `--ago`, or discard).

## Weather

A best-effort snapshot (`ConditionsProvider.get_current_conditions`, 4 s timeout) that never blocks a start/stop. With no coordinates it uses a built-in default location and is marked `location_source: default`.

## Entry points

- Telegram/MCP commands `/mstart`, `/mstop`, `/mlog`, `/mopen`, `/mhistory`, `/mdiscard` (MCP tool `alfred_metric`).
- `POST /metrics/quick/{start,stop,log}`; the entry `source` is taken from `X-Alfred-Client`: `shortcut`, `web` -> portal, otherwise `mcp`.
- **Natural language** (typed or Telegram voice, like tasks): intents `metric.start`, `metric.stop`, `metric.log`, `metric.open` in `intent_examples.py`, with arg extraction schemas (`MetricStartArgs`, ...) in `extraction_service.py` whose field names match the handler's argument keys (`series`, `tags`, `ago`, `value`). Misrouted phrases are fixed by adding examples, not resolver logic ([../assistant-layer.md](../assistant-layer.md#natural-language-intents)).

## Stats

`GET /metrics/series/{name}/stats?tag=&days=`: median/p90/mean/min/max over closed entries, broken down by tag, local hour, weekday and weather (rain = at least 0.1 mm in the start snapshot), plus a 30-day vs previous-30-day trend.

- Groups under 5 samples are flagged `low_confidence` and never ranked as "best" (needs two confident groups).
- Closed durations over 6 h are excluded and reported as `excluded_over_cap`.
- Count series only get `n`.

## Portal

`/metrics`, `/metrics/{name}`: series cards, start/stop/log buttons (the browser's geolocation is sent when allowed so the weather matches where you are), stats and breakdowns, paginated history, manual entry, discard. Writes go through `POST /metrics/{series,quick/{action},entries,entries/{id}/discard}` which proxy to the backend and relay its error message. The scoped Shortcut token is a later phase.
