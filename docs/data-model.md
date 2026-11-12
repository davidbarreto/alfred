# Data model

PostgreSQL + pgvector, SQLAlchemy 2.0 `Mapped[]` models, Alembic migrations. Per-feature details (columns, constraints, rules) are in the module docs; this file covers the cross-cutting picture.

## Schemas

| Schema | Holds |
|---|---|
| `core` | chats, sessions, messages, memories, embeddings, working memory, command executions, settings (`reminders.*`, `planning.*`), `overload_log`, `api_requests` |
| `organizer` | tasks, notes, calendar events (+ skips, overrides), contacts, shopping (products, items, wishlist, recurrence), routines, activities, interviews, shared tags |
| `monitoring` | monitors, alerts, executions |
| `finance` | accounts, budgets, categories, transactions, recurring transactions |
| `language` | tracks, grammar scope, chunks (FSRS state), sessions |
| `cs` | programming-practice evidence (Codeforces, LeetCode sync) |
| `study` | study planner: tracks, targeted plans, tags |
| `metrics` | personal measurement log: series, entries, tags |
| `planning` | saved day plans (`day_plans`) |
| `travel` | trips, legs, stays, places, visits, tags |

## Rules

- All migrations go through Alembic and must be reversible (`downgrade` implemented). Never mutate the schema manually. Migrations run on container startup.
- Foreign keys are explicit. Use `ondelete` cascade only where the child has no value without the parent. Where history matters the FK is `RESTRICT` and deletion is refused with a 409 (metrics, shopping products, activities).
- `Base` is a plain `declarative_base()`; it does **not** add `created_at`/`updated_at`. Each new table declares both. Older tables that lack them are not retrofitted.
- Booleans use plain state names (`active`, `enabled`, `all_day`), not `is_`; older `is_*` columns stay until standardised deliberately. State-change timestamps are `<verb>_at`.
- Timestamps: `LocalDateTime` (`app/db/types.py`) stores UTC in `timestamptz` and exposes naive local datetimes; `Date` columns are local calendar dates. Full rules in `CLAUDE.md` (Dates & timezones).
- Enum value sets are defined once in Python (`TASK_CONTEXTS`, `EVENT_AVAILABILITIES`, `EVENT_PRESENCES`) and feed the Pydantic types, the CHECK constraints and the MCP descriptions.

## Notable patterns

- **Write-through cache.** Tasks and notes (Notion), calendar events (Google Calendar) and contacts (Google Contacts) are mirrored in Alfred's DB; Alfred-only columns never leave it. See [architecture.md](architecture.md#write-through-cache) and [integrations.md](integrations.md).
- **Polymorphic memories.** `core.memories` has a `type` discriminator column.
- **Embeddings.** Stored in a generic `core.embeddings` table with `source_id` foreign keys. Treat it as a derived index, not a source of truth; it can be rebuilt.
- **Shared tags.** `organizer.tags` holds the M2M tag tables for tasks, notes and events. Interviews, metrics, finance transactions and activities have their own tag vocabularies. Beware the SQLAlchemy class-name collision (`Tag` vs the organizer tag) when importing.
- **Derived, not stored.** Metric durations are `ended_at - started_at`; calendar occurrences are expanded from an RRULE at read time; routine steps are expanded, not stored per occurrence.
- **Settings in `core.settings`.** Key/value rows namespaced `reminders.<field>` and `planning.<field>`; defaults are constants in the settings services.
- **Seeds.** `db/seeds/*.yaml` are loaded on every deploy from `entrypoint.sh` by insert-only scripts (interview prep questions, language chunks).

## Tables by module

| Module | Tables | Doc |
|---|---|---|
| Interviews | `interview_stories`, `interview_prep_questions`, `interview_story_questions`, `interview_candidate_questions`, `interview_tags` + link tables | [modules/interviews.md](modules/interviews.md) |
| Metrics | `metrics.series`, `metrics.entries`, `metrics.tags`, `entries_tags` | [modules/metrics.md](modules/metrics.md) |
| Reminders & overload | `core.overload_log`, `core.settings` | [modules/reminders-overload.md](modules/reminders-overload.md) |
| Planning | `planning.day_plans`, `organizer.routines`, `routine_steps`, `activities`, `activity_logs`, `activities_tags`, `calendar_event_skips` (migration 080), `calendar_event_overrides` (migration 082) | [modules/planning.md](modules/planning.md) |
| Travel | `travel.trips`, `legs`, `stays`, `places`, `tags`, `trips_tags` (migration 084), `visits`, `places_tags` (migration 085), `legs_transactions`, `stays_transactions`, `visits_transactions` and `calendar_event_id` on legs/stays (migration 086) and visits (migration 087) | [modules/travel.md](modules/travel.md) |
| Shopping | `organizer.shopping_products`, `shopping_items`, `recurrence_items` | [modules/shopping.md](modules/shopping.md) |
