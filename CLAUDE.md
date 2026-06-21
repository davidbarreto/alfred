# Alfred — Personal AI Assistant

## Project Overview
Alfred is a self-hosted personal AI assistant with two main components:
1. **Python backend API** — FastAPI, SQLAlchemy (2.0+ style), Alembic, Pydantic v2
2. **n8n workflows** — Telegram bot as primary interface, sub-workflow architecture

The stack runs on a Contabo VPS via Docker Compose, with nginx as reverse proxy.
Domains: `dbflabs.com` (Alfred stack), `davidbf.com` (personal site).

---

## Repository Structure

alfred/
├── app/
│   ├── api/                   # Routes and API configurations, auth, etc
│   ├── assistant/             # Commands parsing, intents recognition
│   ├── db/                    # DB session
│   ├── features/              # Features
│       └── core/              # Command history, memories, facts, sessions, etc
│       ├── organizer/         # Tasks, notes, event-calendar, etc
│       ├── monitoring/          # Module for monitoring sites and APIs (webscraping, API monitoring)
│       ├── finance/           # Personal finance tracking
│   └── integrations           # Implementation of integrations, Notion, Google Calendar, etc
│   └── nlp                    # NLP functions
│   └── shared                 # General classes shared between all modules. E.g. Storage Provider
├── alembic/
│   └── versions/
├── tests/             # Unit tests
├── infra/             # docker-compose.yml, .env, scripts to reset databases
├── postman/           # Postman collections
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
- Four schemas: `core`, `organizer`, `monitoring`, `finance`
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

### Testing
- Unit tests mock DB and external services; no real I/O
- Use `pytest` with fixtures for DB sessions and app client
- Don't ignore warnings. Solve them whenever possible
- Test file mirrors source structure: `tests/unit/organizer/test_task_service.py` → `app/organizer/services/task_service.py`
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
- **Notion** — write-through cache; Alfred DB is the read layer, Notion is synced async
- **Google Calendar** — same write-through pattern as Notion
- **Telegram** — input only via n8n; never call Telegram API directly from FastAPI
- **Open-Meteo** — weather data for morning briefing workflow (no API key required)