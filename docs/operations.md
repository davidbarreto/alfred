# Operations

Deployment, runtime and infrastructure notes. Services, volumes, startup sequence and deploy workflows are in [docker.md](docker.md); environment variables and settings are in [configuration.md](configuration.md).

## Hosting

- A VPS running Docker Compose, with nginx as reverse proxy.
- Application in `/opt/stacks/alfred/`, persistent data in `/srv/data/alfred/`.
- Compose files and env live in `infra/` (`docker-compose.yml`, `.env`, postgres-init scripts).

## Rules

- **Docker Compose:** environment variables are injected at runtime; never bake secrets into images.
- **Migrations:** `alembic upgrade head` runs as part of container startup (`entrypoint.sh`), not manually. The same entrypoint loads the insert-only seed scripts.
- **nginx:** shared snippets for SSL termination and proxy headers; do not duplicate config per service.
- **Containers run in UTC** (no `TZ` set), so the server clock is not the user's clock. See `CLAUDE.md` (Dates & timezones).

## API caller identity

Every service that calls the backend API sends an `X-Alfred-Client` header (`web`, `mcp`, `n8n`; `claude` for direct calls made by Claude). `ApiRequestLoggingMiddleware` records one `core.api_requests` row per request (missing header becomes `unknown`) for the Insights "API & MCP Usage" charts.

New callers, and new n8n HTTP Request nodes hitting `http://api:8000`, must send it too. `/health` and `/core/api-requests/*` are deliberately not logged.

## Local stack

The local Docker stack (`infra/docker-compose.yml`) builds and runs again, but it is slow. Default to unit tests and code review to verify changes; the production deploy is where the user tests. Start or rebuild the local stack only when a change genuinely needs it and is not covered by unit tests (real container, DB or migration behaviour), and never as a routine step.

## Scheduled workflows

Cron-triggered n8n workflows call backend endpoints:

| Workflow | Schedule | Endpoint / purpose |
|---|---|---|
| `AlfredReminders` | hourly, 08:00-22:00 | `GET /core/reminders/due`, one digest message ([modules/reminders-overload.md](modules/reminders-overload.md)) |
| Morning briefing / evening digest | daily | briefing endpoints (`app/api/routes/briefing.py`) |
| Watchers | cron | monitoring executions and alerts |

A global pause skips reminder runs (they are not logged as overload days); `POST /core/urgency-reset` is also used by Resume.

## Backfill scripts

One-off data scripts live in `backend/scripts/` and are dry-run by default (`--apply` to write). Example: `backfill_task_planning_fields.py` ([modules/planning.md](modules/planning.md#backfill)).
