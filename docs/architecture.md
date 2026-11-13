# Architecture

How Alfred is put together. Day-to-day coding rules live in `CLAUDE.md`; this file explains the shape of the system and why it is built that way.

## Components

Alfred is a self-hosted personal AI assistant with four parts:

1. **Backend API** (`backend/`) — FastAPI, SQLAlchemy 2.0+, Alembic, Pydantic v2, PostgreSQL + pgvector. Owns all business logic and data.
2. **Web portal** (`web/`) — FastAPI + Jinja2 + Tailwind/DaisyUI + HTMX. Browser UI for viewing data and chatting. Holds no business logic; it calls the backend through a thin client (see [portal.md](portal.md)).
3. **n8n workflows** (`n8n/`) — Telegram bot as the primary interface, plus scheduled triggers (reminders, briefing). Sub-workflow architecture.
4. **MCP server** (`mcp/`) — exposes the backend's command catalog as `alfred_*` tools to MCP clients (Claude).

The stack runs on a VPS via Docker Compose, with nginx as reverse proxy. See [docker.md](docker.md) and the runbook in [operations.md](operations.md).

## How the pieces talk

```text
Telegram ──> n8n ──HTTP──> backend API <──HTTP── web portal
                                ^
                                └──HTTP── MCP server <── Claude
```

- Telegram reaches Alfred only through n8n (FastAPI has no Telegram client); n8n HTTP Request nodes call the backend and hold no business logic.
- Every caller identifies itself with an `X-Alfred-Client` header (`web`, `mcp`, `n8n`, plus `claude` for direct calls by Claude); see [docker.md](docker.md#api-caller-identity).
- Commands (`/storyadd`, `/mstart`, ...) are defined once in a registry and reach the backend from Telegram (through n8n), the MCP server and the chat. See [assistant-layer.md](assistant-layer.md).

## Backend layering

```text
route (thin) -> service (logic, logging) -> repository (queries) -> tables (ORM)
                        |
                        └──> provider (StorageProvider / LlmProvider / EmbeddingProvider)
```

- Routes validate input, call a service, return a Pydantic schema.
- Services orchestrate repositories and providers and are the primary logging location.
- Repositories hold every DB query and no business logic.
- Providers are protocols in `app/shared/`; implementations live in `app/integrations/<provider>/`.
- All `Depends()` factories live in `app/dependencies.py` as `Annotated` aliases.

File-level conventions are in `CLAUDE.md` (Module & File Conventions).

## Write-through cache

For external stores (Notion, Google Calendar, Google Contacts), the Alfred DB is the read layer and the external service is the store of record for the fields it knows about. A service writes to the provider and mirrors the result locally; `sync()` pulls changes back in.

Alfred-only fields (for example task `estimate_minutes`, event `availability`) never go to the provider; the service strips them first. Details and the exact rules are in [modules/planning.md](modules/planning.md#alfred-only-fields). Integration inventory and quirks: [integrations.md](integrations.md).

## n8n workflows

- Telegram bot is the primary user interface.
- Use sub-workflow architecture; keep workflows focused and composable.
- All sub-workflows return a consistent `{ success, message }` envelope.
- Data passed between nodes follows the `alfred` envelope pattern.
- Scheduled workflows (reminders hourly 08:00-22:00, morning briefing, evening digest, watchers) are cron triggers that call a backend endpoint and send the result. Reminder logic: [modules/reminders-overload.md](modules/reminders-overload.md).

## Repository structure

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
├── mcp/                           # MCP server (alfred_* tools built from the command catalog)
├── n8n/
├── infra/                         # docker-compose.yml, .env, postgres-init scripts
├── postman/                       # One collection per feature/integration
├── docs/                          # This documentation; docs/plans is gitignored
└── CLAUDE.md
```
