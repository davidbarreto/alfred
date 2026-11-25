# Planning (day plans, routines, activities)

An LLM client (Claude via MCP) plans a day or week from Alfred's data. Alfred only gathers facts and stores what was agreed; it never schedules anything and never sends a notification for any of this.

Keep personal names and routines out of code, fixtures and these docs.

## Alfred-only fields

Tasks gain `estimate_minutes`, `context`, `available_from` (not before); calendar events gain `availability`, `presence`, `travel_minutes`, `routine_id`, `location_id` ([locations.md](locations.md#events-at-a-location)).

`NotionStorageProvider` forwards every non-null record key to Notion, so `TaskService` strips `_ALFRED_ONLY_FIELDS` before every provider call and skips the call entirely when an update touches only those fields. `CalendarEventService` does the same for Google (`_for_google` strips them from every create and update payload) and `sync()` never writes them. One exception goes through Google on purpose: linking an event to a location may fill its empty calendar `location` text with the location's address ([locations.md](locations.md#events-at-a-location)). Event `tags` are Alfred-only too (the Google provider never reads or returns them), so a tags-only update skips Google and works without OAuth.

Enum value sets are defined once (`TASK_CONTEXTS`, `EVENT_AVAILABILITIES`, `EVENT_PRESENCES`) and feed the Pydantic types, the CHECK constraints and the MCP descriptions.

## Routines

`organizer.routines` + `routine_steps` are daily-life rhythm: no done state, no urgency, never notify, never contain travel (see [Travel](#travel)). Two kinds:

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

A log's `done_at` defaults to now; pass an earlier (local, naive) datetime to catch up on something done before, never more than 5 minutes in the future. The portal's "Log done" row has an optional datetime field for this (empty means now); Telegram uses `/activitylog <id> --at <iso>`.

Rule of thumb: if skipping it counts as a miss it is a recurring task, otherwise an activity.

## Day plan (`GET /planning/day`)

`DayPlanService`, MCP `alfred_day_plan get`, 1-7 days. Aggregates events, event-routine steps, travel blocks of unlocated events, scheduled-routine windows, work and office totals, overdue/due/recurring/backlog tasks, study, language quota, shopping, public holidays, trip days, activity suggestions and the saved plan.

- Free slots are intentionally not returned.
- `holidays` (per day, or top level for one day; omitted when none): public holidays from the **first** `HOLIDAY_CALENDARS` calendar only, the planning calendar (`get_planning_holiday_provider`, also used for location holiday hours and the portal calendar's holiday days via `GET /organizer/holidays`), one line per name with its code, `"Natal (PT)"`. The other calendars still show on the dashboard and in the briefing. These calls are not logged in `provider_calls` (the request never commits). A provider failure adds one warning and never fails the plan; with integrations disabled the list is empty. Alfred does not decide which holidays are days off (no change to the work target): that is a `conventions` rule.
- `trips` (per day, or top level for one day; omitted when none): every trip (any status) whose dates include that day, as `{trip_id, name, day, days, agenda, leave_home_at}`. `agenda` is the briefing's `build_agenda` (legs, check-ins/outs and visits that day, times in the zone where they happen); `leave_home_at` (local ISO with offset) only on the local date of the trip's leave-home time. Each trip's detail is loaded once per request.
- `shopping` (omitted when nothing is pending or due) gives counts only: `pending_items`, `due_recurring`, a `suggested_run` and `by_category` (pending items per category name, largest first, unknown as `other`). Enough to tell a pharmacy stop from a supermarket run; the planner fetches item names with `alfred_shopping` only when it places a stop.
- Travel blocks are derived on every request, never stored, and only for events with no location: see [Travel](#travel).
- Overlaps between timeline items are reported in `warnings`, never resolved. The legs the client builds between locations are not in the timeline, so the client checks them against the events itself. A work-tagged event (or one of its routine steps) entirely inside an in-person event tagged with the office tag (a standup during an office day) is not an overlap; anything else inside it (a personal appointment) still is. So office events stay `blocked`; a `free` one would also be left out of routing (no commute, no missing-route warning).
- Tasks missing an estimate/context are named in one warning line each, or only counted when there are more than 5.
- Backlog (undated, non-recurring tasks): one warning when it is cut at the cap of 30 (repository order: urgency, priority, newest first), and one naming the tasks created more than 60 days ago, oldest first, counted over the whole backlog so tasks past the cap still show up. Alfred reserves no time for the backlog: the weekly backlog block is a `conventions` rule the client places.
- Days outside the `workdays` preference (default mon-fri) get a work target of 0 unless `work_minutes` is passed.
- Completing a recurring task that has a deadline advances the deadline to the next cycle (`next_deadline` in `tasks/recurrence.py`), written through `TaskService`.
- `work.committed_minutes` counts work-tagged events plus the saved plan's blocks of work-tagged tasks, overlaps once (`timeline.merged_minutes`).
- Planning preferences live in `core.settings` as `planning.<field>` (`PlanningSettingsService`, `GET/PUT /planning/settings`, form on the portal `/plan` page); unset values turn the related section off.

## Travel

Alfred gives the facts and the client plans the trips. Which places the user goes through and in what order (home between the office and an afternoon event, a stop on the way), when they leave and which mode they take are planning decisions, so Alfred never derives travel between locations: it returns each event's place and the map of saved routes, and the client saves the legs it chose as `transport` blocks.

- **The map:** `preferences.travel_times`, every saved travel time once per request however many days (`[{origin, place, mode, minutes}]`; Home is `home`, other places their location name in lowercase; a route counts both ways unless the reverse is saved). It is the whole network, not only the places of the range, so a leg through a place with no event (home, a shop) is there too.
- **Choosing a mode** is the client's, with two settings in `preferences`: `planning.walk_tolerance_minutes` (default 10: walking wins when it takes at most that much longer than the fastest public transport; car only when it is the only option) and `planning.default_travel_minutes` (default 30, 0 turns the assumption off: what to assume for a leg with no saved route, as a question for the user).
- **Located events** (a `location_id`, in person, not `free`) get no travel blocks. `planning/timeline.py` (`_travel_blocks`, pure) only checks them against the routes (`LocationTravelTimeService.network()`, loaded once per request into a `TravelGraph` of which pairs have a route): a place with no route to or from Home gets "No travel time saved between Home and Dentist: ask the user and offer to save it" (once per plan), and without a Home location "No Home location saved: travel from home to Office is unknown".

- **Events with no location** keep derived blocks: `travel_minutes > 0` gives "Travel to X" / "Travel home from X". With 0, in-person events get `default_travel_minutes` each way (`assumed: true`) except all-day, `free` and remote events and events entirely inside an in-person office-tagged or located event; all of them share **one** `warnings` line for the plan (each series once).
- Event items carry `location` (the location's name when linked, else the calendar's location text) and `location_id`.
- Everything goes through UTC instants, so a DST day keeps elapsed minutes.

## Saved plans (`planning.day_plans`)

Saving a date archives its active version (`archived_at`) and inserts the next; a partial unique index keeps one active plan per date. Blocks need UTC offsets, must start on their date (local), and `ref_id`s are validated against the table their `kind` points at (not a foreign key: plans are history).

### Block kinds

- `event`, `task`, `study_item`, `activity`, `routine_step`, `routine_block` point at a row.
- `work` (focused work that is not a task; counts toward committed work), `transport` (a commute or trip leg: every leg between locations, which the timeline never derives), `meal`, `break` and `other` are free-form and take no `ref_id`.

### Marking blocks

- **Missed:** `POST/DELETE /planning/saved/{id}/blocks/{index}/missed`, the portal "Didn't do it" button or `day_plan miss`/`unmiss` (by date + `ref_id`, or title). It edits that version in place, creates no version, leaves the task open, and the block no longer counts as committed work. Any kind can be flagged; nothing enforces otherwise.
- **Done:** `done`/`undone` (`POST/DELETE .../blocks/{index}/done`, portal "Done" button) flag a block as done the same way and exclude `missed` (setting one clears the other). A block that ended with neither flag is *unmarked*, not known-done.

### Editing and responses

- **Partial edit:** `POST /planning/saved/edit` / `day_plan edit` replaces the blocks of already saved dates whose start falls in `[replace_from, replace_to)` (local HH:MM) with new `items`, keeps every other block and its flags, and writes a new version per date.
- **Compact responses:** `save` and `edit` return only `{id, plan_date, version, blocks}` per date through the MCP/command layer (the `POST /planning/saved` route still returns full plans).
- **Weekly review:** `GET /planning/review?from&to` / `day_plan review` counts per planned thing (events excluded) how often it was planned, done, missed, unmarked (ended, no mark) and upcoming, with the missed dates.

### Preferences returned with every day plan

- **Conventions:** `planning.conventions` is free text (max 2000 chars, edited on `/settings#planning`) returned in the `preferences` of every `GET /planning/day`, so each client applies the user's standing rules without being told again.
- **Travel times:** `travel_times` in the planning settings and `preferences` is a list of `{origin, place, mode, minutes}`: door-to-door minutes between two places (`origin` defaults to `home`, `place` is the destination; e.g. home to office by metro 50 / car 20, office to school by car 20). Since migration 096 they are rows between locations (`organizer.location_travel_times`, [locations.md](locations.md#travel-times)) and no longer a setting: the list shape, the `/plan` form and the `--travel` syntax are unchanged, a list sent to `PUT /planning/settings` replaces every travel time, and a name that is not a location yet becomes one. Home is always `home`; other names are location names in lowercase. Up to 60.
  - Origin, place and mode are lowercased, one entry per (origin, place, mode), a place cannot be its own origin.
  - A trip counts both ways unless the reverse is listed too.
  - Entries stored before origins existed read back as from home.
  - Command syntax `[origin>]place:mode=minutes[,...];...` (`office:metro=50,car=20;office>school:car=20`); on the portal, travel times are edited on each location's page (the old textarea on `/plan` is gone).
  - Also returned in `preferences`, once per request: the map clients route every day with (leave-home times and `transport` blocks, also for days with no event yet, like an office day being planned). Travel times touching archived locations are kept in the list.

## Planning workflow for clients

The recommended flow for an LLM client is the committed skill `.claude/skills/alfred-day-planning/SKILL.md`; this section is the contract it relies on.

- One `get` for the whole week (`days` through Sunday, max 7) is enough: it already carries `saved_plan`, `preferences` and `warnings`. `get_saved` / `review` are only for looking back at last week.
- Personal rules never live in the repo: they belong in `planning.conventions`, `travel_times`, the other `planning.*` preferences and memory, all of which come back in `preferences`. A full skill with names and routines belongs outside the repo, for example as a Claude web skill.
- Save only the dates that changed (`days` is a JSON string); use `edit` for a window inside an already saved day. Mark outcomes with `miss`/`done` rather than re-saving.
- Legs between places are `transport` blocks the client chooses from the travel times; focused non-task work is `work`. Events the client creates at a frequent place (an office day) get `location_id`, so the commute comes from the travel times.
- The mcp container fetches the catalog once at startup, so after adding a kind or action restart it before the client sees it.

## DST

A local day is 23-25 hours. In `expansion.py` and `planning/timeline.py` every sum, difference and comparison goes through UTC instants (`shift_minutes`, `elapsed_minutes`): Python subtracts and compares aware datetimes that share a `tzinfo` by wall clock, which is wrong across a clock change.

## MCP / command layer

See [../assistant-layer.md](../assistant-layer.md): `details` field, JSON-string params for structured input (`save`'s `days`), `build_model()` for 400s.

## Portal

`/plan` (read-only saved plan, week strip, settings), `/routines`, `/activities`, plus the planning fields in the task and event forms. Writes proxy through `web/app/shared/forward.py`.

## Backfill

`backend/scripts/backfill_task_planning_fields.py` maps old `context:*` and duration tags (`30m`, `2h`) onto the new columns; dry-run by default, `--apply` to write, `--rename-area-tags` to also drop the `area:` prefix. It never creates routines or other personal data.
