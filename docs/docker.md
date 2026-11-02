# Docker, volumes and stored files

How the stack runs under Docker Compose and where Alfred keeps files on the host. Everything here comes from `infra/docker-compose.yml`, `infra/.env.example` and `backend/entrypoint.sh`.

## Services

| Service | Image / build | Host port (loopback only) | Depends on | Purpose |
|---|---|---|---|---|
| `db` | `pgvector/pgvector:pg17` | none | none | PostgreSQL + pgvector; also hosts the n8n database |
| `api` | `backend/` (Python 3.12, ffmpeg) | `${BACKEND_PORT}` -> 8000 | `db` (healthy) | FastAPI backend |
| `web` | `web/` | `${WEB_PORT:-8080}` -> 8080 | `api` | Web portal |
| `mcp` | `mcp/` (Python 3.11) | `${MCP_PORT:-9000}` -> 9000 | `api` | MCP server (OAuth 2.1 for Claude clients) |
| `n8n` | `n8nio/n8n:latest` | `${N8N_PORT}` -> 5678 | `db` (healthy) | Telegram bot + cron workflows |

All ports are bound to `127.0.0.1`. In production nginx terminates TLS and proxies to them; nothing is exposed directly.

Networks: the default project network (`api`, `db`, `web`, `n8n`, `mcp` reach each other by service name, for example `http://api:8000`), plus an **external** network `mcp-shared` that only `mcp` joins so other containers on the same VPS can reach it by name. Create it once on the host before the first `up`:

```bash
docker network create mcp-shared
```

(`deploy-infra.yml` does this automatically on the VPS.)

## What happens at startup

1. **`db`** runs `infra/postgres-init/init.sh` the first time the data directory is empty. It creates two restricted roles (the app user `DB_USER` and the n8n user `N8N_DB_USER`) and the n8n database. The API connects as the restricted user (`DATABASE_URL`); migrations run as the admin user (`DATABASE_ADMIN_URL`).
2. **`api`** runs `backend/entrypoint.sh`:
   1. `alembic upgrade head`
   2. downloads/loads the embedding model (cached in the Hugging Face volume)
   3. seeds: intent examples, language tracks, grammar scopes, language chunks, interview prep questions, interview candidate questions (all insert-only)
   4. `uvicorn app.main:app` on port 8000
   The first start is slow (model download); `GET /health` answers when it is ready.
3. **`web`**, **`mcp`** start after `api`. The MCP server fetches the command catalog from the API once at startup.
4. **`n8n`** starts empty. Owner user, credentials and workflows are created by `n8n/setup_n8n.sh` (idempotent; the n8n deploy workflow runs it, or run it by hand with `bash n8n/setup_n8n.sh` after the stack is up).

## Volumes (data that lives on the host)

Every volume is a **bind mount** whose host path comes from `infra/.env`. Nothing is stored in anonymous Docker volumes, so the data survives `docker compose down` and image rebuilds. Locally, point them under `infra/docker_volumes/` (gitignored); on the VPS they live under `/srv/data/alfred/`.

| `.env` variable | Container path | Service | Contents | If lost |
|---|---|---|---|---|
| `DB_DATA_DIR` | `/var/lib/postgresql/data` | `db` | The whole database: tasks, notes, finance, language, memories, embeddings, everything | **Everything is gone.** Back this up (or `pg_dump`) |
| `N8N_DATA_DIR` | `/home/node/.n8n` | `n8n` | n8n's local state (encryption config, settings). Workflows and executions are in the `n8n` database | Re-run `setup_n8n.sh`; credentials are re-imported from templates |
| `STATEMENT_DATA_DIR` | `/data/statements` | `api` | The original bank statement files you uploaded, one per import batch | Imported transactions stay in the database; you lose the ability to re-download the source file |
| `AUDIO_DATA_DIR` | `/data/audio` | `api` | Language audio: shadowing recordings and the pronunciation TTS cache (see below) | Cache regenerates; shadowing recordings are lost |
| `HF_CACHE_DIR` | `/root/.cache/huggingface` | `api` | Downloaded sentence-transformers model | Re-downloaded on next start |
| `MCP_DATA_DIR` | `/data` | `mcp` | SQLite store of registered OAuth clients and tokens | Every connected Claude client must re-authorise |

The `.env` also has `STATEMENT_STORAGE_DIR` and `AUDIO_STORAGE_DIR`: those are the **container-side** paths the app writes to (`/data/statements`, `/data/audio`) and must match the mount targets above. Leave them at the defaults.

### Statement files (`STATEMENT_DATA_DIR`)

When you import a statement through the portal (`/finance/import`) or `POST /finance/imports/commit`, the original upload is saved so it can be downloaded again (`GET /finance/imports/{batch_id}/file`). Layout:

```text
statements/
  <provider>/<sha256-of-content>_<original-filename>
```

`<provider>` is the key of the statement parser that recognised the file (one folder per provider key registered in `app/features/finance/imports/registry.py`). **Deleting an import batch deletes its transactions and its stored file** (`DELETE /finance/imports/{batch_id}`). These files are real financial data: keep the folder private and never copy their contents into the repo (see `CLAUDE.md`, Sensitive data).

### Audio files (`AUDIO_DATA_DIR`)

```text
audio/
  shadowing/<uuid>.ogg          # your shadowing recordings (language sessions)
  production/<uuid>.ogg         # spoken production attempts (speak/retell)
  pronunciation_cache/<lang>/<sha256-of-text>.<format>   # cached pronunciation TTS per phrase
  conversation/<uuid>.ogg       # conversation turns, only if PERSIST_CONVERSATION_AUDIO=true
```

- Recordings arrive as uploads from the portal or Telegram voice messages (via n8n) and are converted to Ogg with ffmpeg (installed in the API image).
- The pronunciation cache is safe to delete; files are re-fetched from the TTS service on demand.
- Conversation audio is **not stored by default** (`PERSIST_CONVERSATION_AUDIO=false`): replies are LLM free text that is practically never repeated, so caching would only grow the disk. Turn it on only if you want to replay old turns.

## Everyday commands

Run from `infra/` (compose reads `infra/.env`):

```bash
docker compose up -d --build            # build and start everything
docker compose up -d --build api        # rebuild one service (runs migrations + seeds on start)
docker compose logs -f api              # follow logs
docker compose ps                       # status
docker compose exec api alembic current # check the migration revision
docker compose down                     # stop (data stays in the bind-mounted folders)
```

The local stack is slow to build; for most changes the unit tests are the faster check (see [operations.md](operations.md#local-stack)).

## CI compose

`infra/docker-compose.ci.yml` is a trimmed stack for the GitHub Actions smoke test (`api-smoke-test.yml`, daily at 06:00 UTC and on demand): database + API with `DISABLE_INTEGRATIONS=true` (null LLM and Notion providers) and throwaway credentials, then the Postman collections run against it with newman. It mirrors production's two-role split on purpose so a migration that forgets to grant the app user access to a new schema fails there.

## Deploys

Each component has its own GitHub Actions workflow triggered by pushes to `main` that touch its path:

| Workflow | Triggers on | What it does on the VPS (`/opt/stacks/alfred`) |
|---|---|---|
| `deploy-api.yml` | `backend/**` | runs the backend tests, then pulls, builds `api`, restarts it and waits for `/health` |
| `deploy-web.yml` | `web/**` | runs the web tests, then pulls, builds and restarts `web` |
| `deploy-mcp.yml` | `mcp/**` | runs the MCP tests, then pulls, builds and restarts `mcp` |
| `deploy-n8n.yml` | `n8n/**` | pulls, restarts `n8n`, runs `setup_n8n.sh` |
| `deploy-infra.yml` | `infra/docker-compose.yml` | pulls, ensures the `mcp-shared` network, runs `docker compose up -d` |

`infra/.env` is **not** in git: it must already exist on the VPS next to the compose file. Changing it does not trigger a deploy; apply it with `docker compose up -d` on the server.
