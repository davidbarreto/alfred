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
│   │   │       ├── monitoring/    # monitors, alerts, executions
│   │   │       └── organizer/     # tasks, notes, calendar_events, contacts, shopping
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
│   │   │   ├── monitoring/        # Monitors, alerts, executions (flat, not sub-modules)
│   │   │   └── organizer/
│   │   │       ├── calendar_events/
│   │   │       ├── contacts/      # Write-through cache against Google Contacts (full CRUD)
│   │   │       ├── notes/
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
│       │                          #   finance, insights, briefing, chat, auth, language
│       └── templates/             # Jinja2 + Tailwind/DaisyUI; partials prefixed with _
├── n8n/
├── infra/                         # docker-compose.yml, .env, postgres-init scripts
├── postman/                       # One collection per feature/integration
└── CLAUDE.md

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
- Five schemas: `core`, `organizer`, `monitoring`, `finance`, `language`
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
- `<Entity>Read` — response model; returned by routes; `model_config = {"from_attributes": True}`
- `<Entity>Filters` — query-parameter class; plain `__init__` (not `BaseModel`), uses `Annotated[X, Query()]`; used via `Depends()` in routes

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

### Commits
- Don't add Co-Authored-By: Claude or similar text in commit messages

---

## Infrastructure Notes

- **Docker Compose** — environment variables injected at runtime; never bake secrets into images
- **Migrations** — run `alembic upgrade head` as part of container startup, not manually
- **nginx** — shared snippets for SSL termination and proxy headers; do not duplicate config per service
- **File layout on VPS** — application in `/opt/stacks/alfred/`, persistent data in `/srv/data/alfred/`

---

## External Integrations
- **Notion** — write-through cache; Alfred DB is the read layer, Notion is the external store (tasks, notes)
- **Google Calendar** — write-through cache via `StorageProvider`; OAuth token stored in `oauth_tokens` table
- **Google Contacts** — write-through cache via `StorageProvider`; full CRUD scope (`contacts`); also supports one-way sync via `/integration/google-contacts/sync`
- **Google (Gemini)** — LLM provider for chat, memory extraction, briefing formatting, session summaries, and language pronunciation analysis (`gemini-2.5-flash` for audio)
- **Open-Meteo** — weather data for morning briefing (no API key required)
- **Telegram** — input only via n8n; never call Telegram API directly from FastAPI