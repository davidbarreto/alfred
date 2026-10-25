# Alfred — Personal AI Assistant

## Project Overview
Alfred is a self-hosted personal AI assistant with three main components:
1. **Python backend API** — FastAPI, SQLAlchemy (2.0+ style), Alembic, Pydantic v2
2. **Web portal** — FastAPI + Jinja2 + Tailwind/DaisyUI + HTMX; browser UI for viewing data and chatting
3. **n8n workflows** — Telegram bot as primary interface, sub-workflow architecture

The stack runs on a Contabo VPS via Docker Compose, with nginx as reverse proxy.
Domains: `dbflabs.com` (Alfred stack), `davidbf.com` (personal site).

---

## Repository Structure

```text
alfred/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── briefing.py
│   │   │       ├── commands.py
│   │   │       ├── core/          # chats, sessions, messages, memories, embeddings, working_memory
│   │   │       ├── finance/       # accounts, budgets, categories, transactions, recurring_transactions
│   │   │       ├── integrations/  # google_calendar, google_contacts (OAuth + sync), llm_calls, provider_calls
│   │   │       ├── language/      # tracks, grammar_scope, chunks, sessions
│   │   │       ├── metrics/       # series, entries, quick (start/stop/log), tags
│   │   │       ├── monitoring/    # monitors, alerts, executions
│   │   │       ├── organizer/     # tasks, notes, calendar_events, contacts, shopping, routines, activities
│   │   │       ├── planning.py    # day plan, planning settings, saved plans
│   │   │       └── study/         # tracks, plans (overview/generate/transitions), settings
│   │   ├── assistant/
│   │   │   ├── commands/          # registry, resolver, executor, per-domain handlers
│   │   │   └── intents/           # intent service, extraction service, examples
│   │   ├── db/                    # Base, session
│   │   ├── dependencies.py        # All FastAPI Depends() factories and type aliases
│   │   ├── features/
│   │   │   ├── briefing/          # Morning briefing: weather, tasks, events, birthdays, holidays, language SRS; LLM formatter
│   │   │   ├── core/
│   │   │   │   ├── chats/
│   │   │   │   ├── command_executions/
│   │   │   │   ├── embeddings/
│   │   │   │   ├── memories/      # Polymorphic; type discriminator column
│   │   │   │   ├── messages/
│   │   │   │   ├── sessions/
│   │   │   │   └── working_memory/
│   │   │   ├── finance/
│   │   │   │   ├── accounts/
│   │   │   │   ├── budgets/
│   │   │   │   ├── categories/
│   │   │   │   ├── recurring_transactions/
│   │   │   │   └── transactions/
│   │   │   ├── language/
│   │   │   │   ├── srs.py         # FSRS-5 algorithm (CardState, next_card_state, is_leech)
│   │   │   │   ├── chunks/        # Vocabulary chunks; FSRS state fields; Pareto-weighted batch
│   │   │   │   ├── grammar_scope/ # Per-track grammar curriculum (active/deferred/mastered)
│   │   │   │   ├── sessions/      # Learning sessions; feeds_srs flag; daily progress
│   │   │   │   └── tracks/        # Language tracks (code, CEFR level, daily_quota, review_mode)
│   │   │   ├── metrics/           # Personal measurement log: series, entries (start/stop, value, count), tags
│   │   │   ├── monitoring/        # Monitors, alerts, executions (flat, not sub-modules)
│   │   │   ├── study/             # Study planner: tracks, targeted plans (backlog + global cap), tags, generator
│   │   │   ├── planning/          # Day-plan aggregation (service, timeline, settings) + saved_plans/
│   │   │   └── organizer/
│   │   │       ├── activities/    # Optional gap fillers + logs + stats (not tasks)
│   │   │       ├── calendar_events/
│   │   │       ├── contacts/      # Write-through cache against Google Contacts (full CRUD)
│   │   │       ├── notes/
│   │   │       ├── routines/      # Daily-life routines + steps; pure expansion.py
│   │   │       ├── shopping/      # Shopping list + wishlist + recurrence
│   │   │       ├── tags/          # Shared M2M tag tables for tasks/notes/events
│   │   │       └── tasks/
│   │   ├── integrations/
│   │   │   ├── google/            # Google LLM provider (Gemini)
│   │   │   ├── google_calendar/   # Client + StorageProvider
│   │   │   ├── google_contacts/   # Client + StorageProvider (write-through CRUD)
│   │   │   ├── http/              # Shared HTTP pagination helpers
│   │   │   ├── llm_calls/         # LLM call logging (tables, repo, schemas)
│   │   │   ├── notion/            # Client + StorageProvider
│   │   │   ├── oauth_tokens/      # Generic OAuth refresh token store
│   │   │   ├── openai/            # OpenAI LLM provider
│   │   │   ├── provider_calls/    # Integration sync log (tables, repo, schemas)
│   │   │   └── sentence_transformers/  # Local embedding provider
│   │   ├── nlp/                   # Text extraction, normalisation, patterns
│   │   └── shared/                # Protocols: StorageProvider, LlmProvider, EmbeddingProvider; domain helpers
│   ├── alembic/
│   │   └── versions/
│   └── tests/                     # All unit tests (flat, mirrors source: test_<module>.py)
├── web/
│   └── app/
│       ├── client.py              # Thin HTTP client wrapping the backend API
│       ├── config.py
│       ├── main.py                # FastAPI app, auth middleware, router registration
│       ├── routes/                # dashboard, tasks, notes, contacts, calendar, shopping,
│       │                          #   finance, insights, briefing, chat, auth, language, cs, study
│       └── templates/             # Jinja2 + Tailwind/DaisyUI; partials prefixed with _
├── n8n/
├── infra/                         # docker-compose.yml, .env, postgres-init scripts
├── postman/                       # One collection per feature/integration
└── CLAUDE.md
```

---

## Architecture Decisions

### Backend
- **SQLAlchemy 2.0+ style** — use `select()`, `session.execute()`, `Mapped[]` annotations; never use legacy `Query` API
- **Pydantic v2** — use `model_config`, `model_validator`, `field_validator`; not v1 decorators
- **Dependency injection** — use `Annotated[X, Depends(y)]` pattern consistently; auth enforced at router level, use dependencies.py to declare my dependencies

- **Explicit imports** — no re-exports via `__init__.py`; always import from the full module path
- **Private helpers** — prefix internal functions with `_`
- **Single responsibility** — split files when a module grows beyond one clear concern

### Database (PostgreSQL + pgvector)
- Schemas: `core`, `organizer`, `monitoring`, `finance`, `language`, `cs` (programming-practice evidence), `study` (study planner), `metrics` (personal measurement log), `planning` (saved day plans)
- Write-through cache pattern for external integrations (Notion, Google Calendar)
- Embeddings stored in a generic `core.embeddings` table with `source_id` foreign keys; treat as a derived index, not source of truth
- `core.memories` is polymorphic with a `type` discriminator column
- All migrations via Alembic; never mutate the DB schema manually

### n8n Workflows
- Telegram bot is the primary user interface
- Use sub-workflow architecture; keep workflows focused and composable
- All sub-workflows return a consistent `{ success, message }` envelope
- Data passed between nodes follows the `alfred` envelope pattern
- HTTP Request nodes call the FastAPI backend; do not embed business logic in n8n directly
- Telegram's `setMyCommands` API hard-limits each command `description` to 256 characters (BadRequest 400 otherwise, which fails `POST /integration/telegram/set-commands` for *all* commands, not just the offending one). When adding or editing a command in `COMMAND_DEFINITIONS` (`app/assistant/commands/registry.py`), keep `description` at 200 characters or less to leave headroom. Telegram also rejects the whole list with `BOT_COMMANDS_TOO_MUCH` when the combined command + description text exceeds ~5.7k characters (well before the documented 100-command cap; 5679 accepted, 5825 rejected on 2026-10-23). Only the daily-use commands listed in `_MENU_COMMANDS` (`app/api/routes/integrations/telegram.py`) are registered with Telegram — add a command there to put it in the `/` menu; the rest still work when typed. `_fit_to_budget` truncates descriptions uniformly if the menu ever exceeds a 5000-char budget.

---

## Module & File Conventions

### Backend feature module layout

Every domain feature lives under `app/features/<domain>/<feature>/` and follows this file structure:

| File | Purpose |
|---|---|
| `tables.py` | SQLAlchemy ORM models (table definitions only; no business logic) |
| `schemas.py` | Pydantic models: `<Entity>Create`, `<Entity>Update`, `<Entity>Read`, `<Entity>Filters` |
| `repository.py` | A single `<Entity>Repository` class; all DB queries live here; no business logic |
| `service.py` | A single `<Entity>Service` class; orchestrates repo + provider calls; no raw DB access |
| `prompts.py` | Static strings used as LLM system prompts or prompt templates |
| `recurrence.py` | Example of a pure utility module — shared domain logic with no DB/IO dependencies |

When a feature needs multiple services (e.g. briefing), use descriptive prefixes: `summary_service.py`, `formatter_service.py`.

### Pydantic schema naming

- `<Entity>Create` — POST request body; all required fields
- `<Entity>Update` — PATCH request body; all fields `Optional`, `exclude_unset=True` in callers
- `<Entity>Read` — response model; returned by routes; `model_config = {"from_attributes": True}`; always exposes `created_at` and `updated_at` for new entities (each new table declares both columns — `Base` is a plain `declarative_base()` and does not add them). Existing tables that lack them are not retrofitted.
- `<Entity>Filters` — query-parameter class; plain `__init__` (not `BaseModel`), uses `Annotated[X, Query()]`; used via `Depends()` in routes
  - Always give the parameter a plain-value default: `offset: Annotated[int, Query(ge=0)] = 0`. Never write `offset: int = Query(0, ge=0)` — that makes the `Query(...)` sentinel object itself the default, which is fine when FastAPI resolves it via `Depends()` but crashes (e.g. `int() argument must be a ... not 'Query'` deep in a repository `.offset()`/`.limit()` call) whenever the `Filters` class is constructed directly, e.g. from a command handler in `app/assistant/commands/handlers/`. Every field a handler might not explicitly pass needs the plain-value form.
  - Caveat: `Annotated[X, Query(...)] = default` breaks FastAPI's Pydantic `TypeAdapter` (`PydanticUserError: ... is not fully defined`) in a `schemas.py` that has `from __future__ import annotations` at the top, because postponed evaluation turns the annotation into a string FastAPI can't resolve. So: new `Filters` classes should skip `from __future__ import annotations` in that file and use the safe `Annotated` form. If a file already has `from __future__ import annotations` (e.g. legacy modules), keep the bare `Query(...)` default instead, and make sure every command handler that constructs that `Filters` class passes every field explicitly (don't rely on the default at all).

### Repository conventions

- One class per file: `class <Entity>Repository`
- Constructor takes only `session: AsyncSession`
- Method names: `get_<entity>`, `get_<entities>`, `create_<entity>`, `update_<entity>`, `delete_<entity>`; domain-specific names allowed (e.g. `complete_occurrence`)
- All queries use SQLAlchemy 2.0 style: `select()`, `session.execute()`, `scalars()`

### Service conventions

- One class per file: `class <Entity>Service`
- Constructor takes `provider: StorageProvider, session: AsyncSession` (or just `session` if no external provider)
- Delegates all DB access to `self._repo`; never calls `session.execute()` directly
- Private helper functions at module level are prefixed with `_`; shared helpers go in a dedicated utility module

### API route conventions

- Thin handlers only: validate input → call service → return schema
- `router = APIRouter(prefix="/...", tags=[...], dependencies=[Depends(require_auth)])`
- All routes return typed Pydantic `response_model`; never return bare `dict`
- Place static path routes (e.g. `/history`) **before** parameterised routes (e.g. `/{id}`) to avoid routing conflicts
- All `Depends()` factories are declared in `app/dependencies.py` as `Annotated` type aliases (e.g. `TaskServiceDep`)

### Integration module layout

External provider integrations live under `app/integrations/<provider>/`:

| File | Purpose |
|---|---|
| `client.py` | Raw HTTP/SDK client; wraps the external API; no business logic |
| `storage_provider.py` | Implements the `StorageProvider` protocol for write-through cache |
| `tables.py` / `schemas.py` / `repository.py` | Only present when the integration persists its own data |

### Web portal conventions

| File / path | Purpose |
|---|---|
| `web/app/routes/<page>.py` | Route handlers; thin — fetch from backend API, pass to template |
| `web/app/templates/<page>.html` | Full-page Jinja2 templates; always extend `base.html` |
| `web/app/templates/_<partial>.html` | HTMX partial templates; prefixed with `_`; never extend `base.html` |
| `web/app/client.py` | Thin async HTTP wrapper around the backend API (`api.get()`, `api.post()`, …) |

HTMX actions target the smallest possible DOM element. Full-page navigation uses standard `<a href>`. Form submissions use `fetch()` + manual DOM update (not `hx-post`) when the response replaces a larger container.

### Portal pagination pattern

All paginated sections in the portal follow the same offset-based pattern:

1. **`limit + 1` trick** — fetch `PAGE_SIZE + 1` items from the API. If the response has more than `PAGE_SIZE` items, there is a next page; slice the list back to `PAGE_SIZE` for rendering.
2. **`_pagination()` helper** — each route module defines:
   ```python
   _PAGE_SIZE = 20  # or appropriate value per page

   def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
       has_next = len(items) > _PAGE_SIZE
       return items[:_PAGE_SIZE], has_next, offset > 0
   ```
3. **HTMX partial routes** — each paginated section has a dedicated `GET /<page>/<section>?offset=N` endpoint that returns only the list partial (not the full page). Prev/Next buttons inside the partial target the section's wrapper `id` with `hx-swap="innerHTML"`.
4. **Variable naming** — use section-namespaced variables to avoid collisions when multiple sections appear on the same page: `memories_offset`, `memories_has_next`, `memories_has_prev`; `wm_offset`, `wm_has_next`, `wm_has_prev`, etc.
5. **Initial page load** — the main page handler fetches a larger batch (e.g. `limit=200`) for stat aggregations and slices the first `PAGE_SIZE` for the initial grid render. Subsequent pages use the HTMX partial route with proper API `offset`.

### Test file naming

Mirror the source path, prefixed with `test_`:
- `tests/test_task_service.py` ← `app/features/organizer/tasks/service.py`
- `tests/test_api_contacts.py` ← `app/api/routes/organizer/contacts.py`

One test class per logical group of behaviour (`TestComputeStreak`, `TestMissedCount`, …). Mock all DB and external I/O; use `AsyncMock` for async repo methods.

---

## Coding Guidelines

### General
- Always cover changes with unit tests
- Always execute all unit tests after finish a change
- Always add Postman tests for new or changed API routes
- Maintain convention across modules: if a pattern changes in one module (e.g. error handling, response shape, repo method naming), apply it to all others
- No dead code — remove unused imports, functions, and commented-out blocks before committing

### Python / FastAPI
- Route handlers stay thin: validate input, call a service, return output
- Business logic lives in service layer (`services/`), not in routers or models
- Database access only through repository functions; no raw queries in service layer
- All endpoints return typed Pydantic response models — no bare `dict`
- Use `HTTPException` with explicit status codes; never let unhandled exceptions reach the client
- Environment config via `pydantic-settings`; never hardcode secrets or URLs

### SQLAlchemy / Alembic
- All models inherit from a shared `Base` with `created_at` / `updated_at` timestamps
- Foreign keys are always explicit; use `ondelete` cascade where appropriate
- Alembic migrations must be reversible (`downgrade` implemented)
- After schema changes, verify all affected modules still align
- Boolean columns use plain adjective/state names (`active`, `enabled`, `all_day`, `case_sensitive`), not an `is_` prefix, and Pydantic fields mirror the column name. Some older columns still use `is_*` (`is_done`, `is_active`, `is_archived`, ...); leave them until they are standardized deliberately, but don't add new ones. State-change timestamps are `<verb>_at` (`archived_at`, `deleted_at`, `completed_at`); prefer a timestamp over a boolean when "when" matters.

### Dates & timezones

- **Storage is UTC.** `LocalDateTime` (`app/db/types.py`) stores a true UTC instant in `timestamptz` and hands Python a *naive datetime in the configured local zone* (`Settings.timezone`, env `TIMEZONE`, default `Europe/Lisbon`). Other timestamps use `DateTime(timezone=True)`. Changing `TIMEZONE` (a move, DST) needs no data migration. `Date` columns (`do_date`, `occurrence_date`, ...) are local calendar dates and are never converted.
- **Containers run in UTC** (no `TZ` is set), so the server's clock is not the user's clock. Never call `date.today()`, `datetime.now()` (naive) or `datetime.utcnow()` for anything the user sees or any "today" boundary. Use the helpers in `app/shared/timezone.py` (backend) / `web/app/shared/timezone.py` (portal):
  - `local_today()` for "today's date"
  - `local_now()` for an aware local "now"
  - `local_naive_now()` for a naive local "now" (to compare with `LocalDateTime` columns)
- `datetime.now(timezone.utc)` is correct for instants: audit timestamps, TTLs/expiry, "N hours ago" durations, dedup markers.
- Day boundaries (start/end of "today") are local midnights: `datetime.combine(local_today(), time.min, tzinfo=local_timezone())`, never UTC midnight.
- Text shown to an LLM or user as "now" must be local with the zone name (`local_now().strftime("... %H:%M %Z")`), not "UTC".
- **DST:** a local day is 23, 24 or 25 hours long, and one hour a year is ambiguous or missing. Do arithmetic across day boundaries on aware datetimes (or UTC instants), never by subtracting naive local datetimes. Recurrence expansion works on naive local time on purpose, so "every Wednesday 20:00" stays at 20:00 across the change.
- Dates grouped from UTC API timestamps (e.g. `created_at[:10]`) must be converted to local first.
- Tests freeze time with `freezegun` (`freeze_time("2026-07-15 23:30:00")` is 00:30 the next day in Lisbon) or patch `local_today`; don't patch `date`/`datetime` in the module under test.

### Logging

Every module that performs business logic, external I/O, or mutation must have a module-level logger:

```python
import logging
logger = logging.getLogger(__name__)
```

**What to log and at which level:**

| Level | When to use |
|---|---|
| `ERROR` | Unrecoverable failures: LLM call failed, external API error, unexpected exception |
| `WARNING` | Unexpected conditions that are handled: auth rejection, OAuth not configured, truncated LLM response |
| `INFO` | Successful mutations (create / update / delete / complete) and high-level operation results |
| `DEBUG` | Read operations, "not found" on expected paths, item counts, internal flow details |

**Log format — always use `%s` style, never f-strings:**

```python
logger.info("Task created: id=%d title=%r", task.id, task.title)
logger.info("Task updated: id=%d fields=%s", task_id, list(data.model_dump(exclude_unset=True).keys()))
logger.debug("Task update: id=%d not found", task_id)
logger.error("LLM call failed: session_id=%s error=%s", session_id, exc)
logger.warning("Auth failed: invalid token")
```

**Where logs belong:**
- **Service layer** — primary logging location; log after every mutation and on significant errors
- **Integration clients** — log external call failures and notable responses (latency, token counts)
- **Auth middleware** — log rejected requests at WARNING
- **Routes** — do NOT add request-level logging; uvicorn.access already covers it; only log if a route contains logic not delegated to a service
- **Repositories** — do NOT log; DB queries are too granular; log at the service layer instead

**Log content rules:**
- Always include the entity ID and 1–2 key identifying fields (name, title, source)
- For updates, log the changed field names, not values (values may be sensitive)
- Never log passwords, tokens, raw user messages, or financial amounts at INFO or above

### Testing
- Unit tests mock DB and external services; no real I/O
- Use `pytest` with fixtures for DB sessions and app client
- Don't ignore warnings. Solve them whenever possible
- Test file mirrors source structure: `tests/test_task_service.py` → `app/features/organizer/tasks/service.py`
- Aim for behaviour coverage, not line coverage — test contracts, not internals
- For every bug fix: first write a unit test that reproduces the bug (it should fail against the unfixed code), then write the fix that makes it pass. Keep the regression test after the fix lands.

### Sensitive data & test fixtures
- Never copy real personal or financial data — names, account/card numbers, amounts, addresses, merchant strings from a real statement, etc. — from a user-provided file into code, test fixtures, Postman collections, or documentation, even as a "quick example." Always invent synthetic equivalents that preserve the shape/format needed for the test (e.g. `"SOME PERSON"` instead of a real name, `*1234` instead of a real card suffix, round invented amounts instead of real ones).
- Treat every file the user pastes or drops for debugging (bank/card statement exports, CSVs, screenshots) as containing real third-party data by default. It's fine to read and analyze it in place; the rule is about what gets written back into the repo.
- Before committing a new fixture derived from a real file, re-read the fixture itself and confirm nothing was copy-pasted verbatim — don't trust that an earlier "I'll anonymize this" intention actually landed in the file.

### Commits
- Don't add Co-Authored-By: Claude or similar text in commit messages
- Commit freely once a change is complete and tested — no need to ask first.
- Never run `git push` (including `--force`/`--force-with-lease`) unless the user explicitly asks for a push in that specific turn. An earlier "commit and push" is not standing permission for the rest of the session — commit and stop, then say the changes are committed locally and ready to push. This matters most on this repo since it's public on GitHub: push is the last checkpoint before anything sensitive that slipped into a commit becomes visible to anyone.

---

## Interview Prep Module

### Stories, Questions, and Assessment Scales

The interview prep module (`organizer.interviews`) helps track behavioral interview preparation with three main features, plus a shared tag vocabulary:

**1. Interview Stories** — STAR framework stories in `interview_stories` table
- Separate columns: `situation`, `task`, `action`, `result` (mandatory; enforces STAR structure)
- `strength` (1-5) — self-assessed quality of the story itself

**2. Prep Questions** — Behavioral interview questions in `interview_prep_questions`
- Linked to stories via `interview_story_questions` join table
- Each link has a `fit_score` (1-5) — how well the story answers that specific question

**3. Candidate Questions** — Questions to ask interviewers in `interview_candidate_questions`
- Categorized (Onboarding, Tech, Culture, Benefits, Logistics, Growth, Work-life)

**Shared tags** (`organizer.interviews.tags`) — one case-insensitive-unique vocabulary (`interview_tags`) attached to both stories (`interview_story_tag_links`) and prep questions (`interview_question_tag_links`), so the same label (e.g. `ownership`, `amazon:bias-for-action`) connects a story to the questions it fits
- Stories and questions take `tags: list[str]` on create/update plus `POST/DELETE .../{id}/tags/{tag}`; names resolve case-insensitively to the existing tag (first spelling wins), missing ones are created
- Filter with `?tag=` on both list endpoints (`/storylist --tag`, `/preplist --tag`); `GET .../tags` on each returns only tags currently in use there
- `GET /organizer/interview-tags` (usage counts), `PATCH /{id}` (rename, 409 on name clash), `DELETE /{id}` manage the vocabulary; tags are not deleted automatically when their last story/question goes away
- The prep question detail page floats stories sharing a tag with the question to the top of the "Link a story" picker
- `db/seeds/interview_prep_questions.yaml` is the versioned question bank (`text` + `tags`), loaded on every deploy by `seed_interview_prep_questions.py` from `entrypoint.sh`. Insert-only: missing questions are added, existing questions with no tags get the YAML tags, nothing is deleted or re-tagged. Matching is by exact `text`, so reword a question in the YAML and the portal together; a question deleted in the portal returns on the next deploy unless it is removed from the YAML too

### Assessment Scales

**Story Strength (1-5)** — Quality of the story itself:
- **1 (Vague/Incomplete):** Missing context, unclear outcome, lacks details
- **2 (Basic):** STAR parts present but generic; no metrics or specifics
- **3 (Good):** Clear story, specific details, shows competency, has some measure of success
- **4 (Strong):** Specific, concrete metrics, clear before/after, demonstrates key competency well
- **5 (Excellent):** Polished, specific, quantified outcome, shows growth/learning, universally compelling

User self-assesses when creating the story. Can be revised later as the story is refined.

**Link Fit (1-5)** — How well the story answers a specific prep question:
- **1 (Poor Fit):** Tangentially related; doesn't directly answer the question
- **2 (Weak Fit):** Related but requires explanation to connect to the question
- **3 (Good Fit):** Directly addresses the question, clearly demonstrates what's being asked
- **4 (Strong Fit):** Perfectly tailored; directly and powerfully answers the question
- **5 (Excellent Fit):** Perfectly tailored; demonstrates competency exactly as the question asks

User assigns when linking a story to a prep question (default 3). Stories are sorted by fit_score (descending) for each question. Both scales are enforced by DB CHECK constraints.

### AI strength suggestion

`POST /organizer/interview-stories/{id}/assess-strength` (and `/storyassess <id>`) asks the LLM for a suggested 1-5 strength plus one improvement tip. It only suggests; it never writes `strength`. Returns 404 for an unknown story, 502 when the LLM fails or returns invalid JSON. Logged to `llm_calls` as `interview_story_strength`. No portal button yet.

### Command formats

The resolver splits positional args on whitespace and gives the *last* `arg_key` the remainder, and MCP reserves the name `action`. So multi-field text can't be positional:
- `/storyadd situation | task | action | result --strength 4 -t leadership,conflict` (single `text` arg, split on `|` in the handler)
- `/candidateadd How is on-call organised? --category Tech`

---

## Metrics Module

Personal measurement log (`metrics` schema). Design and phases: `docs/plans/metrics.md`.

- **Series** (`metrics.series`) = the thing measured (`commute-work`), with a kind: `duration` (start/stop), `value` (one number), `count` (one event). Names are lowercase slugs. Created automatically on first `/mstart` or `/mlog`.
- **Entries** (`metrics.entries`): `started_at`, `ended_at`, `value`, `status` (`open`/`closed`/`discarded`), `source` (`telegram`/`shortcut`/`portal`/`mcp`), start/stop coordinates, `context` JSON (`{start: weather, end: weather}`). Duration is **derived** (`ended_at - started_at`), never stored. Weekday/hour are derived at query time in the configured timezone.
- **Tags** (`metrics.tags` + `entries_tags`, ORM class `MetricTag`) are the options compared inside a series (`bus`, `metro`).
- **No cascades**: every FK is `RESTRICT`. Entries are discarded, series archived or merged; deleting a series with entries is a 409.
- **Start/stop rules**: `stop` closes the latest open entry; a new `start` discards a still-open one; open entries older than 6 h are stale, and a stop that would make an entry last over 6 h is a 409 (backdate with `--ago`, or discard).
- **Weather** is a best-effort snapshot (`ConditionsProvider.get_current_conditions`, 4 s timeout) and never blocks a start/stop; with no coordinates it uses Porto and is marked `location_source: default`.
- **Entry points**: Telegram/MCP commands `/mstart`, `/mstop`, `/mlog`, `/mopen`, `/mhistory`, `/mdiscard` (MCP tool `alfred_metric`), and `POST /metrics/quick/{start,stop,log}` (source taken from `X-Alfred-Client`: `shortcut`, `web`→portal, otherwise `mcp`).
- **Natural language** (typed or Telegram voice, like tasks): intents `metric.start`, `metric.stop`, `metric.log`, `metric.open` in `intent_examples.py`, with arg extraction schemas (`MetricStartArgs`, …) in `extraction_service.py` whose field names match the handler's argument keys (`series`, `tags`, `ago`, `value`). Misrouted phrases are fixed by adding examples, not resolver logic.
- **Stats** (`GET /metrics/series/{name}/stats?tag=&days=`): median/p90/mean/min/max over closed entries, broken down by tag, local hour, weekday and weather (rain = at least 0.1 mm in the start snapshot), plus a 30-day vs previous-30-day trend. Groups under 5 samples are flagged `low_confidence` and never ranked as "best" (needs two confident groups). Closed durations over 6 h are excluded and reported as `excluded_over_cap`. Count series only get `n`.
- **Portal** (`/metrics`, `/metrics/{name}`): series cards, start/stop/log buttons (the browser's geolocation is sent when allowed so the weather matches where you are), stats and breakdowns, paginated history, manual entry, discard. Writes go through `POST /metrics/{series,quick/{action},entries,entries/{id}/discard}` which proxy to the backend and relay its error message. The scoped Shortcut token is a later phase.

---

## Reminders & Overload

Hourly n8n cron (`AlfredReminders`, 08:00-22:00) -> `GET /core/reminders/due` -> one digest message. Logic in `app/features/core/reminders/` (`service.py`, pure rules in `escalation.py`).

- **Escalation depends on priority.** Overdue tasks become URGENT after a grace period (HIGH 0h, MEDIUM 48h, LOW 168h); undated tasks after an age (7/21/45 days). Urgent re-remind cadence also depends on priority (HIGH hourly, MEDIUM 2h, LOW 4h). Escalation is persisted through `TaskService` (Notion write-through) and never reverses by itself; `POST /core/urgency-reset` is the way back.
- **Overload** (`app/features/core/overload/`): `OverloadService.snapshot()` counts overdue/urgent pending tasks and classifies `ok` / `elevated` (half the thresholds) / `overloaded`. Each reminder run upserts one `core.overload_log` row per day (worst level, peaks, runs, tasks listed/omitted). `GET /core/overload/status|history` feed the portal banner (dashboard + tasks) and the Overload section of `/tasks/insights`. Runs skipped by the global pause are not logged, so a pause breaks the "days in a row" streak.
- **While overloaded** the digest lists at most `overload_max_listed` tasks (urgent first), adds "+K more", slows urgent reminders to `overload_urgent_interval_hours`, and prefixes a header. Only listed tasks get a dedup marker, so the rest rotate into later runs. A one-off "Backlog cleared" line is sent when the level returns to `ok`.
- **Catch-up plan** (`app/features/core/catchup/`, deliberately not called "triage": the language module already uses `pending_triage` for chunks): `CatchupService.get_suggestions()` recomputes on every call (nothing stored) and returns today's top 3 plus suggestions: `spread` (re-date overdue one-off tasks at most `catchup_tasks_per_day` per day from tomorrow, keeping time of day, skipping the top 3 and the stale ones), `drop` (non-HIGH tasks overdue, or undated and urgent, for `catchup_stale_days`+ days) and `habits` (recurring tasks with `catchup_missed_habit_threshold`+ misses this week; informational only). `apply` re-validates against fresh data and writes through `TaskService` (drop = status `CANCELLED`, spread = new deadline). Surfaces: `GET /core/catchup`, `POST /core/catchup/apply`, Telegram `/catchup` and `/catchupapply spread|drop <ids>` (not in the `_MENU_COMMANDS` menu, so type them), and the "Catch up" button of the portal banner. Nothing is ever applied without an explicit accept.
- **Settings** live in `core.settings` as `reminders.<field>` (`ReminderSettingsService`, `GET/PUT /core/reminder-settings`, form under Overload in `/tasks/insights`); defaults are constants in `settings_service.py`, `urgency_reset_days` falls back to its env var. `UNDATED_TASK_SNOOZE_DAYS` is still env-only.

---

## Planning (day plans, routines, activities)

An LLM client (Claude via MCP) plans a day or week from Alfred's data. Alfred only gathers facts and stores what was agreed; it never schedules anything and never sends a notification for any of this. The design notes live in `docs/plans/day-planning.md` (gitignored: it names real people and routines, so keep personal names out of code, fixtures and this file).

- **Alfred-only fields.** Tasks gain `estimate_minutes`, `context`, `available_from` (not before); calendar events gain `availability`, `presence`, `travel_minutes`, `routine_id`. `NotionStorageProvider` forwards every non-null record key to Notion, so `TaskService` strips `_ALFRED_ONLY_FIELDS` before every provider call and skips the call entirely when an update touches only those fields; `CalendarEventService` does the same for Google and `sync()` never writes them. Enum value sets are defined once (`TASK_CONTEXTS`, `EVENT_AVAILABILITIES`, `EVENT_PRESENCES`) and feed the Pydantic types, the CHECK constraints and the MCP descriptions.
- **Routines** (`organizer.routines` + `routine_steps`) are daily-life rhythm: no done state, no urgency, never notify, never contain travel (that is the event's `travel_minutes`). Two kinds: *event-based* (attached to event series through `calendar_events.routine_id`; steps use `anchor` start/end + `offset_minutes`) and *scheduled* (an RRULE + `starts_on`; steps use a `window_start`/`window_end`, and a window exactly as long as the duration is a fixed time). `routines/expansion.py` expands steps with pure functions; nothing is stored per occurrence.
- **Activities** (`organizer.activities`, `activity_logs`, tags through `activities_tags`) are optional gap fillers, not tasks: logging one is what counts as done, `target_per_week` is a soft wish used only for suggestions, archiving keeps the logs (FK `RESTRICT`). Rule of thumb: if skipping it counts as a miss it is a recurring task, otherwise an activity.
- **`GET /planning/day`** (`DayPlanService`, MCP `alfred_day_plan get`, 1-7 days) aggregates events, event-routine steps, derived travel blocks, scheduled-routine windows, work and office totals, overdue/due/recurring/backlog tasks, study, language quota, shopping, activity suggestions and the saved plan. Free slots are intentionally not returned. Overlaps are reported in `warnings`, never resolved. Days outside the `workdays` preference (default mon-fri) get a work target of 0 unless `work_minutes` is passed. Completing a recurring task that has a deadline advances the deadline to the next cycle (`next_deadline` in `tasks/recurrence.py`), written through `TaskService`. Planning preferences live in `core.settings` as `planning.<field>` (`PlanningSettingsService`, `GET/PUT /planning/settings`, form on the portal `/plan` page); unset values turn the related section off.
- **Saved plans** (`planning.day_plans`): saving a date archives its active version (`archived_at`) and inserts the next; a partial unique index keeps one active plan per date. Blocks need UTC offsets, must start on their date (local), and `ref_id`s are validated against the table their `kind` points at (not a foreign key: plans are history).
- **DST.** A local day is 23-25 hours. In `expansion.py` and `planning/timeline.py` every sum, difference and comparison goes through UTC instants (`shift_minutes`, `elapsed_minutes`): Python subtracts and compares aware datetimes that share a `tzinfo` by wall clock, which is wrong across a clock change.
- **MCP/command layer.** Command definitions take an optional `details` field (not sent to Telegram, appended to the MCP tool description) for enum values, units, formats and workflow; `description` stays one line, `details` only adds to it. MCP params are strings, so structured input (`save`'s `days`) is a JSON string validated by the handler with a 400 message. Handlers build models with `build_model()` so bad input is a 400, not a 500.
- **Portal.** `/plan` (read-only saved plan, week strip, settings), `/routines`, `/activities`, plus the planning fields in the task and event forms. Writes proxy through `web/app/shared/forward.py`.
- **Backfill.** `backend/scripts/backfill_task_planning_fields.py` maps old `context:*` and duration tags (`30m`, `2h`) onto the new columns; dry-run by default, `--apply` to write, `--rename-area-tags` to also drop the `area:` prefix. It never creates routines or other personal data.

---

## Infrastructure Notes

- **Docker Compose** — environment variables injected at runtime; never bake secrets into images
- **Migrations** — run `alembic upgrade head` as part of container startup, not manually
- **API caller identity** — every service that calls the backend API sends an `X-Alfred-Client` header (`web`, `mcp`, `n8n`); `ApiRequestLoggingMiddleware` records one `core.api_requests` row per request (missing header → `unknown`) for the Insights "API & MCP Usage" charts. New callers (or new n8n HTTP Request nodes hitting `http://api:8000`) must send it too. `/health` and `/core/api-requests/*` are deliberately not logged
- **nginx** — shared snippets for SSL termination and proxy headers; do not duplicate config per service
- **File layout on VPS** — application in `/opt/stacks/alfred/`, persistent data in `/srv/data/alfred/`
- **The local Docker stack (`infra/docker-compose.yml`) build issue has been fixed** — it's runnable again, but default to unit tests and code review to verify changes; the user tests in production themselves. Only start/rebuild the local stack when a change genuinely needs it and isn't covered by unit tests (e.g. verifying real container/DB/migration behavior) — don't reach for it as a routine step on every change.

---

## External Integrations
- **Notion** — write-through cache; Alfred DB is the read layer, Notion is the external store (tasks, notes)
- **Google Calendar** — write-through cache via `StorageProvider`; OAuth token stored in `oauth_tokens` table
- **Google Contacts** — write-through cache via `StorageProvider`; full CRUD scope (`contacts`); also supports one-way sync via `/integration/google-contacts/sync`
- **Google (Gemini)** — LLM provider for chat, memory extraction, briefing formatting, session summaries, and language pronunciation analysis (`gemini-2.5-flash` for audio)
- **Open-Meteo** — weather data for morning briefing (no API key required)
- **Telegram** — input only via n8n; never call Telegram API directly from FastAPI