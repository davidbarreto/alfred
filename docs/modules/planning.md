# Planning (day plans, routines, activities)

An LLM client (Claude via MCP) plans a day or week from Alfred's data. Alfred only gathers facts and stores what was agreed; it never schedules anything and never sends a notification for any of this.

The design notes live in `docs/plans/day-planning.md` (gitignored: it names real people and routines, so keep personal names out of code, fixtures and these docs).

## Alfred-only fields

Tasks gain `estimate_minutes`, `context`, `available_from` (not before); calendar events gain `availability`, `presence`, `travel_minutes`, `routine_id`.

`NotionStorageProvider` forwards every non-null record key to Notion, so `TaskService` strips `_ALFRED_ONLY_FIELDS` before every provider call and skips the call entirely when an update touches only those fields. `CalendarEventService` does the same for Google and `sync()` never writes them. Event `tags` are Alfred-only too (the Google provider never reads or returns them), so a tags-only update skips Google and works without OAuth.

Enum value sets are defined once (`TASK_CONTEXTS`, `EVENT_AVAILABILITIES`, `EVENT_PRESENCES`) and feed the Pydantic types, the CHECK constraints and the MCP descriptions.

## Routines

`organizer.routines` + `routine_steps` are daily-life rhythm: no done state, no urgency, never notify, never contain travel (that is the event's `travel_minutes`). Two kinds:

- *Event-based* — attached to event series through `calendar_events.routine_id`; steps use `anchor` start/end + `offset_minutes`.
- *Scheduled* — an RRULE + `starts_on`; steps use a `window_start`/`window_end`, and a window exactly as long as the duration is a fixed time.

`routines/expansion.py` expands steps with pure functions; nothing is stored per occurrence.

## Skipping, moving and ending recurring events

Alfred stores one master row with an RRULE and expands it in `CalendarEventService.get_events`.

### Skip

`skip`/`unskip` (`POST/DELETE /organizer/calendar-events/{id}/skips`, commands `/eventskip`, `/eventunskip`, MCP `alfred_event`) record a date in `organizer.calendar_event_skips` (migration 080); the expansion leaves that date out, so lists, the day plan, reminders and notifications all honour it. Skips are Alfred-only (the meeting still exists for everyone else, Google is never told) and the date must be a real occurrence.

### End the series

`endseries` (`POST .../end-series`, `/eventend`) rewrites the rule with `UNTIL` via `recurrence.end_rule_before` (UTC instant for timed events, a date for all-day ones, replacing any `UNTIL`/`COUNT`) and goes through `update_event`, so it is written through to Google. It refuses a date that would not shorten the series. `delete` still removes the whole series. The portal day view shows both actions on recurring events and the edit form lists skipped dates to restore.

### Move one occurrence

`reschedule`/`unreschedule` (`POST /organizer/calendar-events/{id}/overrides` body `occurrence_date` + new `start_datetime`/`end_datetime`, `DELETE .../overrides/{date}`, commands `/eventreschedule`, `/eventunreschedule`; `/move` is already the alias of `update`) record the new span in `organizer.calendar_event_overrides` (migration 082, keyed by the date the *series* has the occurrence on).

- `get_events` replaces the original span with the override, lists it where it is now (even if that is outside the range the series' own occurrence falls in) and skip wins over a move.
- Unlike skip it **is written through to Google**: `CalendarEventService.reschedule_occurrence` calls `provider.update` with the Google instance id (`recurrence.occurrence_instance_id`: series id + `_` + original start as UTC `YYYYMMDDTHHMMSSZ`), which creates an exception of that instance, and stores the times Google answers with. Restoring writes the original span back.
- All-day occurrences and skipped dates are refused, and `end_series` drops overrides on or after the new end.
- `sync()` turns Google's modified instances (`recurringEventId` + `originalStartTime`) into overrides of their series instead of standalone events (and deletes a standalone copy imported by an earlier sync), so a move made in Google shows up in Alfred too.
- **The instance id format and the exception write are untested against real Google.**

**Portal:** the day view (`/calendar/day/{date}`) has a clock-edit button on recurring timed events that opens a dialog (date, start, end in the app's time zone; `POST /calendar/{id}/move` -> `/overrides`), a "moved" badge plus a put-back button on moved ones (`DELETE /calendar/{id}/move/{date}`), and the edit form lists moved dates as chips. `_add_occurrence_dates` tags each occurrence with the date the series has it on (`occurrence_date`, found by matching the occurrence's start against the series' `overrides`), and skip, move and end-series use that date, not the displayed one.

## Activities

`organizer.activities`, `activity_logs`, tags through `activities_tags`. Optional gap fillers, not tasks: logging one is what counts as done, `target_per_week` is a soft wish used only for suggestions, archiving keeps the logs (FK `RESTRICT`).

Rule of thumb: if skipping it counts as a miss it is a recurring task, otherwise an activity.

## Day plan (`GET /planning/day`)

`DayPlanService`, MCP `alfred_day_plan get`, 1-7 days. Aggregates events, event-routine steps, derived travel blocks, scheduled-routine windows, work and office totals, overdue/due/recurring/backlog tasks, study, language quota, shopping, activity suggestions and the saved plan.

- Free slots are intentionally not returned.
- Overlaps are reported in `warnings`, never resolved.
- Days outside the `workdays` preference (default mon-fri) get a work target of 0 unless `work_minutes` is passed.
- Completing a recurring task that has a deadline advances the deadline to the next cycle (`next_deadline` in `tasks/recurrence.py`), written through `TaskService`.
- `work.committed_minutes` counts work-tagged events plus the saved plan's blocks of work-tagged tasks, overlaps once (`timeline.merged_minutes`).
- Planning preferences live in `core.settings` as `planning.<field>` (`PlanningSettingsService`, `GET/PUT /planning/settings`, form on the portal `/plan` page); unset values turn the related section off.

## Saved plans (`planning.day_plans`)

Saving a date archives its active version (`archived_at`) and inserts the next; a partial unique index keeps one active plan per date. Blocks need UTC offsets, must start on their date (local), and `ref_id`s are validated against the table their `kind` points at (not a foreign key: plans are history).

### Block kinds

- `event`, `task`, `study_item`, `activity`, `routine_step`, `routine_block` point at a row.
- `work` (focused work that is not a task; counts toward committed work), `transport` (a commute or trip leg not already covered by an event's `travel_minutes`), `meal`, `break` and `other` are free-form and take no `ref_id`.

### Marking blocks

- **Missed:** `POST/DELETE /planning/saved/{id}/blocks/{index}/missed`, the portal "Didn't do it" button or `day_plan miss`/`unmiss` (by date + `ref_id`, or title). It edits that version in place, creates no version, leaves the task open, and the block no longer counts as committed work. Any kind can be flagged; nothing enforces otherwise.
- **Done:** `done`/`undone` (`POST/DELETE .../blocks/{index}/done`, portal "Done" button) flag a block as done the same way and exclude `missed` (setting one clears the other). A block that ended with neither flag is *unmarked*, not known-done.

### Editing and responses

- **Partial edit:** `POST /planning/saved/edit` / `day_plan edit` replaces the blocks of already saved dates whose start falls in `[replace_from, replace_to)` (local HH:MM) with new `items`, keeps every other block and its flags, and writes a new version per date.
- **Compact responses:** `save` and `edit` return only `{id, plan_date, version, blocks}` per date through the MCP/command layer (the `POST /planning/saved` route still returns full plans).
- **Weekly review:** `GET /planning/review?from&to` / `day_plan review` counts per planned thing (events excluded) how often it was planned, done, missed, unmarked (ended, no mark) and upcoming, with the missed dates.

### Preferences returned with every day plan

- **Conventions:** `planning.conventions` is free text (max 2000 chars, form on `/plan`) returned in the `preferences` of every `GET /planning/day`, so each client applies the user's standing rules without being told again.
- **Travel times:** `planning.travel_times` is a list of `{origin, place, mode, minutes}`: door-to-door minutes between two places (`origin` defaults to `home`, `place` is the destination; e.g. home to office by metro 50 / car 20, office to school by car 20).
  - Origin, place and mode are lowercased, one entry per (origin, place, mode), a place cannot be its own origin, max 20.
  - A trip counts both ways unless the reverse is listed too.
  - Entries stored before origins existed read back as from home.
  - Command syntax `[origin>]place:mode=minutes[,...];...` (`office:metro=50,car=20;office>school:car=20`); form on `/plan` (one line per entry, `place, mode, minutes` or `origin, place, mode, minutes`).
  - Also returned in `preferences`, so clients derive leave-home times and `transport` blocks for days with no event (office days are decided inside the plan, so they have no event to carry `travel_minutes`).

## DST

A local day is 23-25 hours. In `expansion.py` and `planning/timeline.py` every sum, difference and comparison goes through UTC instants (`shift_minutes`, `elapsed_minutes`): Python subtracts and compares aware datetimes that share a `tzinfo` by wall clock, which is wrong across a clock change.

## MCP / command layer

See [../assistant-layer.md](../assistant-layer.md): `details` field, JSON-string params for structured input (`save`'s `days`), `build_model()` for 400s.

## Portal

`/plan` (read-only saved plan, week strip, settings), `/routines`, `/activities`, plus the planning fields in the task and event forms. Writes proxy through `web/app/shared/forward.py`.

## Backfill

`backend/scripts/backfill_task_planning_fields.py` maps old `context:*` and duration tags (`30m`, `2h`) onto the new columns; dry-run by default, `--apply` to write, `--rename-area-tags` to also drop the `area:` prefix. It never creates routines or other personal data.
