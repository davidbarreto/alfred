# Alfred — Personal AI Assistant

## Project Overview
Alfred is a self-hosted personal AI assistant with four components:
1. **Python backend API** (`backend/`) — FastAPI, SQLAlchemy (2.0+ style), Alembic, Pydantic v2
2. **Web portal** (`web/`) — FastAPI + Jinja2 + Tailwind/DaisyUI + HTMX; browser UI for viewing data and chatting
3. **n8n workflows** (`n8n/`) — Telegram bot as primary interface, sub-workflow architecture
4. **MCP server** (`mcp/`) — exposes the command catalog as `alfred_*` tools to Claude

The stack runs on a VPS via Docker Compose, with nginx as reverse proxy.

## Where to read more

This file holds the rules that apply to every change. Reference material lives in `docs/` and is **not** loaded automatically: read the relevant file before working in that area.

| Read | Before |
|---|---|
| `docs/architecture.md` | Changing how components talk, adding a service, or needing the full repo tree |
| `docs/data-model.md` | Adding or changing tables, schemas or migrations |
| `docs/integrations.md` | Touching Notion, Google, Gemini/OpenAI, Open-Meteo or Telegram code |
| `docs/assistant-layer.md` | Adding or editing a command, intent example, MCP tool or the Telegram menu |
| `docs/portal.md` | Adding or changing a portal page, partial or paginated section |
| `docs/operations.md` | Touching Docker, deploy, migrations on startup, cron workflows or `X-Alfred-Client` |
| `docs/docker.md` | Changing compose services, volumes, startup/seed steps, deploy workflows, or where audio/statement files are stored |
| `docs/configuration.md` | Adding or changing an env variable, a runtime setting (`core.settings`) or an auth path |
| `docs/features.md` | Needing to know what a module does, or where a feature is exposed (portal / commands / API); update it when adding a user-facing feature |
| `docs/modules/interviews.md` | Interview stories, prep questions, candidate questions, interview tags |
| `docs/modules/metrics.md` | Metrics series/entries, `/mstart` and friends |
| `docs/modules/reminders-overload.md` | Reminders, urgency escalation, overload, catch-up |
| `docs/modules/planning.md` | Day plans, saved plans, routines, activities, recurring-event skip/move, Alfred-only task/event fields |
| `docs/modules/shopping.md` | Shopping list, products, wishlist, recurrence |
| `docs/plans/` | Design notes per feature (gitignored: they name real people and routines, so never copy personal names into code, fixtures or docs) |

When you change behaviour a module doc describes, update that doc in the same commit.

---

## Repository Map

```text
alfred/
├── backend/app/
│   ├── api/routes/        # Thin FastAPI routers, grouped by schema (core, organizer, finance, ...)
│   ├── assistant/         # commands/ (registry, resolver, executor, handlers), intents/
│   ├── features/          # <domain>/<feature>/: tables, schemas, repository, service
│   ├── integrations/      # Notion, Google, OpenAI, sentence-transformers, llm_calls, ...
│   ├── shared/            # Protocols (StorageProvider, LlmProvider, EmbeddingProvider), timezone helpers
│   ├── dependencies.py    # All FastAPI Depends() factories and type aliases
│   └── db/                # Base, session, custom types
├── backend/alembic/versions/
├── backend/tests/         # Flat, mirrors source: test_<module>.py
├── web/app/               # client.py, routes/, templates/ (see docs/portal.md)
├── mcp/  n8n/  infra/  postman/  docs/
```

Full tree: `docs/architecture.md`.

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
- Schemas: `core`, `organizer`, `monitoring`, `finance`, `language`, `cs`, `study`, `metrics`, `planning` (what each holds: `docs/data-model.md`)
- Write-through cache pattern for external integrations (Notion, Google Calendar, Google Contacts)
- Embeddings live in a generic `core.embeddings` table; treat as a derived index, not source of truth
- `core.memories` is polymorphic with a `type` discriminator column
- All migrations via Alembic; never mutate the DB schema manually

### n8n Workflows
- Telegram bot is the primary user interface; Telegram is input only via n8n, never call its API from FastAPI
- Use sub-workflow architecture; keep workflows focused and composable
- All sub-workflows return a consistent `{ success, message }` envelope
- Data passed between nodes follows the `alfred` envelope pattern
- HTTP Request nodes call the FastAPI backend; do not embed business logic in n8n directly
- Keep each command `description` in `COMMAND_DEFINITIONS` at 200 characters or less: Telegram rejects the *whole* menu (not just one command) above 256 per description or ~5.7k combined. Only commands in `_MENU_COMMANDS` are registered with Telegram. Details: `docs/assistant-layer.md`

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

Route handlers in `web/app/routes/` stay thin: fetch from the backend API through `web/app/client.py`, pass to a template. Full pages extend `base.html`; HTMX partials are prefixed `_` and never extend it. Paginated sections use the `limit + 1` / `_pagination()` pattern. Full conventions: `docs/portal.md`.

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

## Infrastructure Rules

- Environment variables are injected at runtime; never bake secrets into images
- Migrations run as `alembic upgrade head` on container startup, not manually
- Every service that calls the backend API must send an `X-Alfred-Client` header (`web`, `mcp`, `n8n`, `claude`), including new n8n HTTP Request nodes hitting `http://api:8000`
- The local Docker stack (`infra/docker-compose.yml`) works but is slow: default to unit tests and code review; the user tests in production. Start or rebuild it only when a change genuinely needs real container/DB/migration behaviour
- More: `docs/operations.md`
