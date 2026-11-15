# Dates & Timezones

- **Storage is UTC.** `LocalDateTime` (`app/db/types.py`) stores a true UTC instant in `timestamptz` and hands Python a *naive datetime in the configured local zone* (`Settings.timezone`, env `TIMEZONE`, default set in `Settings.timezone`). Other timestamps use `DateTime(timezone=True)`. Changing `TIMEZONE` (a move, DST) needs no data migration. `Date` columns (`do_date`, `occurrence_date`, ...) are local calendar dates and are never converted.
- **Containers run in UTC** (no `TZ` is set), so the server's clock is not the user's clock. Never call `date.today()`, `datetime.now()` (naive) or `datetime.utcnow()` for anything the user sees or any "today" boundary. Use the helpers in `app/shared/timezone.py` (backend) / `web/app/shared/timezone.py` (portal):
  - `local_today()` for "today's date"
  - `local_now()` for an aware local "now"
  - `local_naive_now()` for a naive local "now" (to compare with `LocalDateTime` columns)
- `datetime.now(timezone.utc)` is correct for instants: audit timestamps, TTLs/expiry, "N hours ago" durations, dedup markers.
- Day boundaries (start/end of "today") are local midnights: `datetime.combine(local_today(), time.min, tzinfo=local_timezone())`, never UTC midnight.
- Text shown to an LLM or user as "now" must be local with the zone name (`local_now().strftime("... %H:%M %Z")`), not "UTC".
- **DST:** a local day is 23, 24 or 25 hours long, and one hour a year is ambiguous or missing. Do arithmetic across day boundaries on aware datetimes (or UTC instants), never by subtracting naive local datetimes. Recurrence expansion works on naive wall time on purpose, so "every Wednesday 20:00" stays at 20:00 across the change; calendar events expand in the event's own `timezone` (falling back to the local zone) and convert each occurrence to local time, so a series set in another zone keeps its wall time there and moves in local time when either zone changes its clocks.
- Dates grouped from UTC API timestamps (e.g. `created_at[:10]`) must be converted to local first.
- Tests freeze time with `freezegun` (`freeze_time("2026-07-15 23:30:00")` is already the next day in the configured zone) or patch `local_today`; don't patch `date`/`datetime` in the module under test.
