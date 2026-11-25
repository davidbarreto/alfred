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
| `docs/conventions.md` | Adding a feature module, schema, repository, service, route, integration, migration or log line (layout, naming, `Filters` gotchas, Alembic details, logging rules) |
| `docs/dates-and-timezones.md` | Touching anything with dates, times, "today", DST or `LocalDateTime` |
| `docs/testing.md` | Writing tests: mocking rules, `@pytest.mark.db`, CI smoke job, fixtures from real files |
| `docs/architecture.md` | Changing how components talk, adding a service, or needing the full repo tree |
| `docs/data-model.md` | Adding or changing tables, schemas or migrations |
| `docs/integrations.md` | Touching Notion, Google, Gemini/OpenAI, Open-Meteo or Telegram code |
| `docs/assistant-layer.md` | Adding or editing a command, intent example, MCP tool or the Telegram menu |
| `docs/portal.md` | Adding or changing a portal page, partial or paginated section |
| `docs/operations.md` | Running or debugging anything on prod or CI: deploy checks, logs, restarts, migrations, database access, one-off scripts, a failed smoke test |
| `docs/docker.md` | Changing compose services, volumes, startup/seed steps, deploy workflows, cron workflows, `X-Alfred-Client`, or where audio/statement files are stored |
| `docs/configuration.md` | Adding or changing an env variable, a runtime setting (`core.settings`) or an auth path |
| `docs/features.md` | Needing to know what a module does, or where a feature is exposed (portal / commands / API); update it when adding a user-facing feature |
| `docs/modules/interviews.md` | Interview stories, prep questions, candidate questions, interview tags |
| `docs/modules/metrics.md` | Metrics series/entries, `/mstart` and friends |
| `docs/modules/reminders-overload.md` | Reminders, urgency escalation, overload, catch-up |
| `docs/modules/planning.md` | Day plans, saved plans, routines, activities, recurring-event skip/move, Alfred-only task/event fields |
| `docs/modules/shopping.md` | Shopping list, products, wishlist, recurrence |
| `docs/modules/locations.md` | Frequent places (home, office, shops), opening hours, what they sell |

When you change behaviour a module doc describes, update that doc in the same commit.

---

## Repository Map

```text
alfred/
├── backend/app/
│   ├── api/routes/        # Thin FastAPI routers, grouped by schema
│   ├── assistant/         # commands/ (registry, resolver, executor, handlers), intents/
│   ├── features/          # <domain>/<feature>/: tables, schemas, repository, service
│   ├── integrations/      # Notion, Google, OpenAI, sentence-transformers, llm_calls, ...
│   ├── shared/            # protocols/ (provider contracts), utils/ (timezone, time_text, tags, links, ...)
│   ├── dependencies.py    # All FastAPI Depends() factories and type aliases
│   └── db/                # Base, session, custom types
├── backend/alembic/versions/
├── backend/tests/         # Flat, mirrors source: test_<module>.py
├── web/app/               # client.py, routes/, templates/
├── mcp/  n8n/  infra/  postman/  docs/
```

Full tree: `docs/architecture.md`.

---

## Architecture Decisions

### Backend
- **SQLAlchemy 2.0+ style**: `select()`, `session.execute()`, `Mapped[]`; never the legacy `Query` API
- **Pydantic v2**: `model_config`, `model_validator`, `field_validator`; not v1 decorators
- **Dependency injection**: `Annotated[X, Depends(y)]` consistently; auth enforced at router level; declare dependencies in `dependencies.py`
- **Explicit imports**: no re-exports via `__init__.py`; always import from the full module path
- **Private helpers**: prefix internal functions with `_`
- **Single responsibility**: split files when a module grows beyond one clear concern
- **Layering**: routes are thin (validate, call service, return a typed Pydantic `response_model`, never a bare `dict`); business logic in services; DB access only in repositories; use `HTTPException` with explicit status codes. Naming and file layout: `docs/conventions.md`
- Environment config via `pydantic-settings`; never hardcode secrets or URLs

### Database (PostgreSQL + pgvector)
- Schemas: `core`, `organizer`, `monitoring`, `finance`, `language`, `cs`, `study`, `metrics`, `planning` (what each holds: `docs/data-model.md`)
- Write-through cache pattern for external integrations (Notion, Google Calendar, Google Contacts)
- Alfred-only columns (e.g. task `estimate_minutes`, event `availability`) never go to the provider: the service strips them before every provider call and skips the call when an update touches only those fields
- Embeddings live in a generic `core.embeddings` table; treat as a derived index, not source of truth
- `core.memories` is polymorphic with a `type` discriminator column
- All migrations via Alembic and reversible; never mutate the DB schema manually
- **A migration is edited only while unpushed.** Once any commit touching it has been pushed, add a new migration instead
- **Squash unpushed migration commits.** When several unpushed commits change the same migration file, squash them so the file is introduced (or changed) in one commit. Likewise squash when a later unpushed commit reverts an earlier one (add then delete, or delete then add, the same change): the net result must not carry the back-and-forth
- New boolean columns: plain names (`active`, `enabled`), no `is_` prefix. Timestamps `<verb>_at`. Tags are stored trimmed and lowercase via `normalize_tag_name`. More: `docs/conventions.md`

### Dates & timezones (summary)
Storage is UTC and containers run in UTC. Never call `date.today()`, naive `datetime.now()` or `datetime.utcnow()` for anything the user sees; use `local_today()` / `local_now()` / `local_naive_now()` from `app/shared/utils/timezone.py` (portal: `web/app/shared/timezone.py`). Day boundaries are local midnights. Read `docs/dates-and-timezones.md` before touching date logic.

### n8n Workflows
- Telegram bot is the primary user interface; Telegram is input only via n8n, never call its API from FastAPI
- Use sub-workflow architecture; keep workflows focused and composable
- All sub-workflows return a consistent `{ success, message }` envelope
- Data passed between nodes follows the `alfred` envelope pattern
- HTTP Request nodes call the FastAPI backend; do not embed business logic in n8n directly
- Keep each command `description` in `COMMAND_DEFINITIONS` at 200 characters or less: Telegram rejects the *whole* menu (not just one command) above 256 per description or ~5.7k combined. Only commands in `_MENU_COMMANDS` are registered with Telegram. Details: `docs/assistant-layer.md`

### Web portal
Route handlers stay thin and fetch through `web/app/client.py`. Lay pages out with the classes in `web/app/static/css/portal.css` (`page`, `page-head`, `card-row`, `split`, ...), never a bare `grid-cols-2` for cards: every page must work at phone width and in dark mode. **Cap list-like cards**: a detail page shows only the first 5 plus a "See all N" link to a **separate page**; never an in-place expand, never an unbounded list. Full conventions: `docs/portal.md`.

---

## Coding Guidelines

- Always cover changes with unit tests, and execute all unit tests (backend and web suites) after finishing a change
- Always add Postman tests for new or changed API routes
- Maintain convention across modules: if a pattern changes in one module, apply it to all others
- No dead code: remove unused imports, functions and commented-out blocks before committing
- Every module with business logic, external I/O or mutation has a module-level `logger = logging.getLogger(__name__)`. Use `%s` style (never f-strings); log mutations at INFO in the service layer, not in routes or repositories; never log passwords, tokens, raw user messages or financial amounts at INFO or above. Details: `docs/conventions.md`
- Tests: mock DB and external I/O; no real I/O. For every bug fix, first write a test that reproduces it (fails on the unfixed code), then fix. Don't ignore warnings. Backend tests need `ALFRED_API_TOKEN=test-api-token` (if you see mass `401 == 200` failures, a real token is in the shell: `env -u ALFRED_API_TOKEN .venv/bin/python -m pytest`). Details: `docs/testing.md`
- **Sensitive data:** never copy real personal or financial data (names, account/card numbers, amounts, merchant strings) from a user-provided file into code, fixtures, Postman collections or docs. Invent synthetic equivalents, and re-read any fixture derived from a real file before committing. Treat every pasted or dropped file as real third-party data. Prompts and `persona.md` say "the user": the user's name and personal persona text live only in `core.settings` (`assistant.*`, portal `/settings#assistant`). Details: `docs/testing.md`

### Commits
- Don't add Co-Authored-By: Claude or similar text in commit messages
- Commit freely once a change is complete and tested; no need to ask first
- Never run `git push` (including `--force`/`--force-with-lease`) unless the user explicitly asks for a push in that specific turn. An earlier "commit and push" is not standing permission for the rest of the session: commit and stop, then say the changes are committed locally and ready to push. This repo is public on GitHub: push is the last checkpoint before anything sensitive that slipped into a commit becomes visible.

---

## Infrastructure Rules

- Environment variables are injected at runtime; never bake secrets into images, and never commit `infra/.env`
- nginx uses shared snippets for SSL termination and proxy headers; don't duplicate config per service
- Production is read-only by default: never create or edit files on the VPS by hand (not even for testing); files reach it through commit, push and deploy. Confirm a deploy with `gh run view <id>`, not `gh run watch --exit-status`
- Migrations run as `alembic upgrade head` on container startup, not manually
- Every service that calls the backend API must send an `X-Alfred-Client` header (`web`, `mcp`, `n8n`, `claude`), including new n8n HTTP Request nodes hitting `http://api:8000`
- The local Docker stack (`infra/docker-compose.yml`) works but is slow: default to unit tests and code review; the user tests in production. Start or rebuild it only when a change genuinely needs real container/DB/migration behaviour
- Commands for checking and debugging prod and CI: `docs/operations.md`; services, volumes and deploy workflows: `docs/docker.md`
