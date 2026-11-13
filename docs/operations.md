# Operations

Runbook for running, checking and debugging Alfred: commands and procedures only. What the services, volumes and deploy workflows are is in [docker.md](docker.md); environment variables are in [configuration.md](configuration.md).

## Where things are

| What | Where |
|---|---|
| Production host | `ssh david@davidbf.com` (Contabo VPS) |
| App checkout and compose files | `/opt/stacks/alfred/` (`infra/docker-compose.yml`, `infra/.env`) |
| Persistent data (DB, audio, statements, n8n, MCP) | `/srv/data/alfred/` |

Production is read-only by default: do not create or edit files on the VPS by hand (not even for testing). Files reach it through commit, push and deploy.

On the VPS, every command below uses this alias:

```bash
COMPOSE="docker compose -f /opt/stacks/alfred/infra/docker-compose.yml --project-directory /opt/stacks/alfred/infra"
```

## Check a deploy

Each push to `main` triggers the deploy workflow of the component it touches (see [docker.md](docker.md#deploys)).

```bash
gh run list --limit 10                      # recent runs of every workflow
gh run view <id>                            # conclusion and failed step
gh run view <id> --log-failed               # logs of the failing steps only
```

Always confirm the result with `gh run view <id>`: `gh run watch --exit-status` has reported success on a failed `deploy-api.yml` run.

Re-run a deploy without a new commit: `gh workflow run deploy-api.yml` (also `deploy-web`, `deploy-mcp`, `deploy-n8n`, `deploy-infra`).

## Service status and logs (VPS)

```bash
$COMPOSE ps                                 # status of all services
$COMPOSE logs --tail 200 api                # last 200 lines
$COMPOSE logs -f --since 10m api            # follow, starting 10 minutes back
$COMPOSE exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"
```

Same for `web`, `mcp`, `n8n` and `db`. The first start after a deploy is slow (migrations, seeds, embedding model warm-up); `/health` answers when the API is ready.

## Restart, rebuild, apply `.env` changes (VPS)

```bash
$COMPOSE up -d api                          # recreate one service with the current image
$COMPOSE build api && $COMPOSE up -d api    # rebuild from the checked-out code, then restart
$COMPOSE up -d                              # apply a changed infra/.env (it is not in git and does not trigger a deploy)
bash /opt/stacks/alfred/n8n/setup_n8n.sh    # re-import n8n credentials and workflows (idempotent)
```

Normal code changes go through push and deploy instead of a manual build.

## Migrations

Migrations run on API start (`entrypoint.sh` runs `alembic upgrade head`, then the insert-only seeds). To inspect or step through them:

```bash
$COMPOSE exec api alembic current           # revision the database is on
$COMPOSE exec api alembic history | head    # latest revisions
$COMPOSE exec api alembic downgrade -1      # undo the newest one (confirm first on production)
$COMPOSE exec api alembic upgrade head      # reapply
```

## Database access (VPS)

The `db` container already has the admin credentials in its environment:

```bash
$COMPOSE exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'                        # interactive psql
$COMPOSE exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from core.tasks"'
```

Backup: stream the dump to your own machine, so no file is written on the VPS:

```bash
ssh david@davidbf.com 'docker compose -f /opt/stacks/alfred/infra/docker-compose.yml --project-directory /opt/stacks/alfred/infra exec -T db sh -c "pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\""' > alfred-$(date +%F).sql
```

The database holds everything and the data directory is not otherwise backed up (see [docker.md](docker.md#volumes-data-that-lives-on-the-host)).

## Scripts against the real database

One-off scripts live in `backend/scripts/` and are part of the API image. `diagnose_*` and `ledger_trace.py` only read; `backfill_*` and `fix_*` are dry-run by default and write only with `--apply`.

```bash
$COMPOSE exec -T api python scripts/diagnose_opening_balance_overlap.py
$COMPOSE exec -T api python scripts/backfill_task_planning_fields.py            # dry run, prints a diff
$COMPOSE exec -T api python scripts/backfill_task_planning_fields.py --apply    # writes (confirm first)
```

Each script's docstring lists its arguments. Example write-up: [modules/planning.md](modules/planning.md#backfill).

## Cron workflows (n8n)

Scheduled work (reminders, briefings, watchers) runs as n8n cron workflows that call backend endpoints (table in [docker.md](docker.md#cron-workflows)). To check one:

```bash
$COMPOSE logs --since 2h n8n                # n8n side: did it fire, did the HTTP node fail
$COMPOSE logs --since 2h api | grep "GET /core/reminders/due"   # backend side: did the call arrive
```

A global pause skips reminder runs; clear it with the portal's Resume button or `POST /core/urgency-reset`.

## Troubleshoot the API smoke test (CI)

`api-smoke-test.yml` builds `infra/docker-compose.ci.yml` and runs the Postman collections against it with newman. It is one job (`smoke-test`), runs next to the deploys and never gates them.

```bash
gh run list --workflow=api-smoke-test.yml   # find the run
gh run view <id> --log-failed               # failing steps' logs
gh run download <id> -n api-log             # full API container log (uploaded only on failure)
gh workflow run api-smoke-test.yml          # manual run; add -f migration_roundtrip=true to also downgrade and re-upgrade the newest migration
```

Where to look, in order:

1. **Run summary page** (Actions tab, or `gh run view <id>`): the `Failed assertions` step writes a `## Failed Postman assertions` section with one block per collection holding only the failing assertions. Start here for a Postman failure.
2. **Step logs**: the full newman output is in `Run Postman collections` (`==> <collection>` headers separate collections). Other steps fail on their own: `Build and start API + DB` (image build or compose error), `Wait for API to be ready` (prints the `api` log after 300 s, usually a migration or startup crash), `Migration round trip` (prints `alembic current` before and after; runs only when a push adds or edits a file in `backend/alembic/versions`), `Real-database tests (pytest -m db)`.
3. **`Check API logs for errors`**: fails the job on any `ERROR:` line even when every assertion passed (a swallowed exception, a failing background task). It prints the matching lines with line numbers and counts `WARNING:` lines (mostly expected 4xx from negative tests, not failing).
4. **`api-log` artifact**: the context around an `ERROR:` line, or a 500 that the assertions only show as a status code.

Reproduce locally (slow: read the artifact first):

```bash
docker compose -f infra/docker-compose.ci.yml up -d --build
cd postman && newman run <collection>.collection.json -e environment.json \
  --env-var base_url=http://localhost:8000 --env-var api_token=ci-smoke-test-token
docker compose -f infra/docker-compose.ci.yml down -v
```

`cs` and `study` run only `--folder ci-safe`; the Google, Telegram and `language` collections are not run (the workflow header says why).

Common causes:

- Assertions expecting real LLM output fail legitimately: CI uses null LLM and Notion providers (`DISABLE_INTEGRATIONS=true`); prune or guard them.
- A migration that forgets to grant the app role access to a new schema fails at startup or on first request: CI mirrors production's two-role split on purpose.
- Tests that create uniquely-named rows (tags, categories) need a per-run name, because migrations seed rows.

## Local stack

```bash
cd infra && docker compose up -d --build    # build and start everything (slow)
docker compose logs -f api
docker compose down                         # data stays in the bind-mounted folders
```

Default to unit tests and code review; start the local stack only for real container, DB or migration behaviour. Unit tests need `ALFRED_API_TOKEN=test-api-token`; on mass `401 == 200` failures run `env -u ALFRED_API_TOKEN .venv/bin/python -m pytest` from `backend/`.
