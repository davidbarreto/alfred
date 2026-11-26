# Data model

PostgreSQL + pgvector, SQLAlchemy 2.0 `Mapped[]` models, Alembic migrations. Per-feature details (columns, constraints, rules) are in the module docs; this file covers the cross-cutting picture.

## Schemas

| Schema | Holds |
|---|---|
| `core` | chats, sessions, messages, memories, embeddings, working memory, command executions, settings (`reminders.*`, `planning.*`, `assistant.*`), `overload_log`, `api_requests` |
| `organizer` | tasks, notes, calendar events (+ skips, overrides), contacts, shopping (products, items, wishlist, recurrence), locations, routines, activities, interviews, shared tags |
| `monitoring` | monitors, alerts, executions |
| `finance` | accounts, budgets, categories, transactions, recurring transactions |
| `language` | tracks, grammar scope, chunks (FSRS state), sessions |
| `cs` | programming-practice evidence (Codeforces, LeetCode sync) |
| `study` | study planner: tracks, targeted plans, tags |
| `metrics` | personal measurement log: series, entries, tags |
| `planning` | saved day plans (`day_plans`) |
| `travel` | trips, legs, stays, places, visits, tags, links |
| `location` | geography shared by every domain: countries, cities |

## Conventions

Migrations, foreign keys, `created_at`/`updated_at`, boolean and timestamp naming, enum value sets and date handling are rules for every change: see `CLAUDE.md` (SQLAlchemy / Alembic, Dates & timezones).

## Notable patterns

- **Write-through cache.** Tasks and notes (Notion), calendar events (Google Calendar) and contacts (Google Contacts) are mirrored in Alfred's DB; Alfred-only columns never leave it. See [architecture.md](architecture.md#write-through-cache) and [integrations.md](integrations.md).
- **Polymorphic memories.** `core.memories` has a `type` discriminator column.
- **Embeddings.** Stored in a generic `core.embeddings` table with `source_id` foreign keys. Treat it as a derived index, not a source of truth; it can be rebuilt.
- **Shared tags.** `organizer.tags` holds the M2M tag tables for tasks, notes and events. Interviews, metrics, finance transactions and activities have their own tag vocabularies. Beware the SQLAlchemy class-name collision (`Tag` vs the organizer tag) when importing.
- **Derived, not stored.** Metric durations are `ended_at - started_at`; calendar occurrences are expanded from an RRULE at read time; routine steps are expanded, not stored per occurrence.
- **Settings in `core.settings`.** Key/value rows namespaced `reminders.<field>`, `planning.<field>`, `assistant.<field>` and others; defaults are constants in the settings services. Personal text (persona additions, the user's name) lives here, never in the repository; the home address is the Home place's (`location.places`).
- **Seeds.** `db/seeds/*.yaml` are loaded on every deploy from `entrypoint.sh` by insert-only scripts (interview prep questions, language chunks).

## Tables by module

| Module | Tables | Doc |
|---|---|---|
| Interviews | `interview_stories`, `interview_prep_questions`, `interview_story_questions`, `interview_candidate_questions`, `interview_tags` + link tables | [modules/interviews.md](modules/interviews.md) |
| Metrics | `metrics.series`, `metrics.entries`, `metrics.tags`, `entries_tags` | [modules/metrics.md](modules/metrics.md) |
| Reminders & overload | `core.overload_log`, `core.settings` | [modules/reminders-overload.md](modules/reminders-overload.md) |
| Planning | `planning.day_plans`, `organizer.routines`, `routine_steps`, `activities`, `activity_logs`, `activities_tags`, `calendar_event_skips` (migration 080), `calendar_event_overrides` (migration 082) | [modules/planning.md](modules/planning.md) |
| Travel | `travel.trips`, `legs`, `stays`, `places`, `tags`, `trips_tags` (migration 084), `visits`, `places_tags` (migration 085), `legs_transactions`, `stays_transactions`, `visits_transactions` and `calendar_event_id` on legs/stays (migration 086) and visits (migration 087), `links` (migration 090; migration 092 lets a link belong to a city or country too), `countries` and `cities` (migration 091; migration 093 adds `default_tag_names` to both and the trips' own `home_city_id` / `home_address` / `airport_buffer_min` / `home_to_airport_min`; `places.city_id` replaces the text `city` / `country`, legs gain `origin_city_id` / `destination_city_id`, `trip_weather.city_id` replaces `city_key` / `city`) | [modules/travel.md](modules/travel.md) |
| Location | `location.countries`, `location.cities`: `travel.countries` / `travel.cities` moved by migration 100 (`ALTER TABLE ... SET SCHEMA`: same ids and foreign keys, indexes renamed `*_travel_*` → `*_location_*`); migration 103 adds the cities' `latitude` / `longitude` and `cover_path` / `cover_credit` / `cover_source_url` on both (the files live under `MEDIA_DATA_DIR`), and `travel.trips.photo_album_url`; `location.residences` (migration 104: places lived, city RESTRICT, one birth row and one open row at most) | [modules/places.md](modules/places.md#cities-and-countries), [modules/travel.md](modules/travel.md) (*Cities and countries*) |
| Shopping | `organizer.shopping_products`, `shopping_items`, `recurrence_items` | [modules/shopping.md](modules/shopping.md) |
| Places | `location.places` (migration 101: `travel.places` moved, `organizer.locations` merged in); `organizer.everyday_places` (the everyday role), `organizer.places_shopping_categories`, `organizer.travel_times`; `calendar_events.place_id` (SET NULL). History: `organizer.locations` (migrations 094-099: Home from the old `organizer.home_address` setting in 095, travel times in 096, events in 097, fixed kinds in 098, coordinates in 099) | [modules/places.md](modules/places.md) |
