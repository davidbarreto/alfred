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

## Troubleshooting the API smoke test

`api-smoke-test.yml` (build + Postman collections against `infra/docker-compose.ci.yml`, see [docker.md](docker.md#ci-compose)) is a single job, `smoke-test`. It runs next to the deploys and never gates them, so a red run does not stop a deploy. Find it with `gh run list --workflow=api-smoke-test.yml`, then open it with `gh run view <id>` (add `--log-failed` for the failing steps' logs).

Where to look, in order:

1. **Run summary page** (Actions tab, or `gh run view <id>`): the `Failed assertions` step writes a `## Failed Postman assertions` section with one block per collection, holding only the failing newman assertions. Start here for a Postman failure. The same text is printed at the end of that step's log, and each affected collection also gets an `::error` annotation.
2. **Step logs**: the full newman output of every collection is in the `Run Postman collections` step (`==> <collection>` headers separate them). Other steps fail on their own: `Build and start API + DB` (image build or compose error), `Wait for API to be ready` (prints the `api` container log after 300 s, usually a migration or startup crash), `Migration round trip` (prints `alembic current` before and after, only runs when a push adds or edits a file in `backend/alembic/versions`), `Real-database tests (pytest -m db)`.
3. **`Check API logs for errors` step**: fails the job on any `ERROR:` line in the API log even when every Postman assertion passed (a swallowed exception, a failing background task). The matching lines are printed with line numbers, plus the count of `WARNING:` lines (mostly the expected 4xx from negative tests, not failing).
4. **`api-log` artifact**: on failure the full API container log (`infra/api.log`) is uploaded as an artifact on the run page (`gh run download <id> -n api-log`). Use it for the context around an `ERROR:` line or a 500 that the assertion output only shows as a status code.

Reproducing: the same stack runs locally with `docker compose -f infra/docker-compose.ci.yml up -d --build` and `newman run postman/<collection>.collection.json -e postman/environment.json --env-var base_url=http://localhost:8000 --env-var api_token=ci-smoke-test-token` (the local stack is slow, see [Local stack](#local-stack): prefer reading the artifact first). The `cs` and `study` collections run only their `ci-safe` folder (`--folder ci-safe`), and the Google, Telegram and `language` collections are not run at all (the header comment of the workflow lists why).

Common causes:

- Assertions that expect real LLM output fail legitimately: CI uses null LLM/Notion providers (`DISABLE_INTEGRATIONS=true`), so prune or guard those assertions rather than chase the API.
- A migration that forgets to grant the app role access to a new schema fails at startup or on first request: CI mirrors production's two-role split on purpose.
- Postman tests that create uniquely-named rows (tags, categories) must use a per-run name, because migrations seed rows.
- Manual runs: `gh workflow run api-smoke-test.yml` (add `-f migration_roundtrip=true` to also downgrade the newest migration and upgrade again).

## Backfill scripts

One-off data scripts live in `backend/scripts/` and are dry-run by default (`--apply` to write). Example: `backfill_task_planning_fields.py` ([modules/planning.md](modules/planning.md#backfill)).
