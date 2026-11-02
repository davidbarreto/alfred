# Reminders & overload

Hourly n8n cron (`AlfredReminders`, 08:00-22:00) -> `GET /core/reminders/due` -> one digest message. Logic in `app/features/core/reminders/` (`service.py`, pure rules in `escalation.py`).

## Escalation

Escalation depends on priority.

- Overdue tasks become URGENT after a grace period (HIGH 0h, MEDIUM 48h, LOW 168h); undated tasks after an age (7/21/45 days).
- Urgent re-remind cadence also depends on priority (HIGH hourly, MEDIUM 2h, LOW 4h).
- Escalation is persisted through `TaskService` (Notion write-through) and never reverses by itself; `POST /core/urgency-reset` is the way back.

## Overload

`app/features/core/overload/`: `OverloadService.snapshot()` counts overdue/urgent pending tasks and classifies `ok` / `elevated` (half the thresholds) / `overloaded`.

- Each reminder run upserts one `core.overload_log` row per day (worst level, peaks, runs, tasks listed/omitted).
- `GET /core/overload/status|history` feed the portal banner (dashboard + tasks) and the Overload section of `/tasks/insights`.
- Runs skipped by the global pause are not logged, so a pause breaks the "days in a row" streak.

**While overloaded** the digest lists at most `overload_max_listed` tasks (urgent first), adds "+K more", slows urgent reminders to `overload_urgent_interval_hours`, and prefixes a header. Only listed tasks get a dedup marker, so the rest rotate into later runs. A one-off "Backlog cleared" line is sent when the level returns to `ok`.

## Catch-up plan

`app/features/core/catchup/`. Deliberately not called "triage": the language module already uses `pending_triage` for chunks.

`CatchupService.get_suggestions()` recomputes on every call (nothing stored) and returns today's top 3 plus suggestions:

- `spread` — re-date overdue one-off tasks at most `catchup_tasks_per_day` per day from tomorrow, keeping time of day, skipping the top 3 and the stale ones.
- `drop` — non-HIGH tasks overdue, or undated and urgent, for `catchup_stale_days`+ days.
- `habits` — recurring tasks with `catchup_missed_habit_threshold`+ misses this week; informational only.

`apply` re-validates against fresh data and writes through `TaskService` (drop = status `CANCELLED`, spread = new deadline). Surfaces: `GET /core/catchup`, `POST /core/catchup/apply`, Telegram `/catchup` and `/catchupapply spread|drop <ids>` (not in the `_MENU_COMMANDS` menu, so type them), and the "Catch up" button of the portal banner. Nothing is ever applied without an explicit accept.

## Settings

Live in `core.settings` as `reminders.<field>` (`ReminderSettingsService`, `GET/PUT /core/reminder-settings`, form under Overload in `/tasks/insights`). Defaults are constants in `settings_service.py`; `urgency_reset_days` falls back to its env var. `UNDATED_TASK_SNOOZE_DAYS` is still env-only.
