# Alfred

A self-hosted personal AI assistant: tasks, notes, calendar, contacts, shopping, finance, language practice, metrics, interview prep and day planning, reachable from Telegram, a web portal and Claude (via MCP). Everything runs from one Docker Compose stack.

See [docs/features.md](docs/features.md) for what each module does.

## Components

| Directory | What it is |
|---|---|
| `backend/` | FastAPI API (SQLAlchemy 2.0, Alembic, Pydantic v2, PostgreSQL + pgvector) |
| `web/` | Web portal (FastAPI + Jinja2 + Tailwind/DaisyUI + HTMX) |
| `n8n/` | Telegram bot and scheduled workflows (reminders, briefings, watchers) |
| `mcp/` | MCP server exposing Alfred's commands as tools |
| `infra/` | Docker Compose, env template and Postgres init script |
| `postman/` | One Postman collection per feature/integration |

## Requirements

- Docker with the Compose plugin
- Accounts and keys for what you want to use. The backend **will not start** without a Notion integration (API key and two database IDs) and a Google OAuth client; a Gemini API key is needed for chat and the language features; a Telegram bot token for the bot. The full list is in [docs/configuration.md](docs/configuration.md).
- For development outside Docker: Python 3.12 (backend) and 3.11+ (web, mcp)

## Install and run (Docker)

```bash
git clone <repository-url> alfred
cd alfred/infra

# 1. Configure
cp .env.example .env
$EDITOR .env          # fill in secrets, URLs and the *_DATA_DIR folders (see below)

# 2. Create the host folders referenced by the *_DATA_DIR variables
#    (locally, anything under infra/docker_volumes/ works; it is gitignored)
mkdir -p docker_volumes/{postgres_data,n8n_data,hf_cache_data,audio,statements,mcp}

# 3. One-time network used by the MCP server
docker network create mcp-shared

# 4. Build and start
docker compose up -d --build
docker compose logs -f api     # first start downloads the embedding model; wait for "Application startup complete"
```

Then:

| What | Where (loopback; put nginx in front for the internet) |
|---|---|
| Web portal | `http://127.0.0.1:${WEB_PORT}` (default 8080), log in with `WEB_PASSWORD` |
| Backend API + Swagger UI | `http://127.0.0.1:${BACKEND_PORT}/docs` (send `Authorization: Bearer $ALFRED_API_TOKEN`) |
| n8n editor | `http://127.0.0.1:${N8N_PORT}` (default 5678) |
| MCP server | `http://127.0.0.1:${MCP_PORT}` (default 9000) |
| Health check | `GET /health` on the API |

On every start the API container applies database migrations and loads the seed data, so there is no separate migration step ([docs/docker.md](docs/docker.md#what-happens-at-startup)).

### First-run setup

1. **Database data folder.** On Linux the Postgres container runs as uid 999; `chown -R 999:999` the folder behind `DB_DATA_DIR`.
2. **n8n.** Create the owner, import credentials and workflows (idempotent, safe to re-run): `bash n8n/setup_n8n.sh` from the repo root. It reads `infra/.env`.
3. **Telegram menu.** Register the command menu once: `POST /integration/telegram/set-commands` on the API with the bearer token.
4. **Google Calendar and Contacts.** Open `GET /integration/google-calendar/oauth/url` (and the contacts equivalent) in a browser, approve, and the callback stores the refresh token. `GET .../status` confirms the connection.
5. **MCP clients.** Add `MCP_PUBLIC_URL` as a remote MCP server in Claude; it authenticates with OAuth and the `MCP_LOGIN_PASSWORD`.

### Where your data lives

Everything persistent is a bind-mounted host folder: the database, uploaded bank statements, language audio, the model cache, n8n state and MCP OAuth tokens. **Back up the database folder** (or use `pg_dump`) and the statements folder. What each folder contains and what happens if you lose it: [docs/docker.md](docs/docker.md#volumes-data-that-lives-on-the-host).

## Day-to-day commands

From `infra/`:

```bash
docker compose up -d --build api      # rebuild and restart one service
docker compose logs -f api            # follow logs
docker compose down                   # stop; data stays in the host folders
```

## Run the tests

Each component has its own pytest suite; none needs a database or network.

```bash
cd backend && python -m pytest tests/ -q
cd web     && python -m pytest tests/ -q
cd mcp     && python -m pytest tests/ -q
```

Set up a virtualenv per component first (`backend`: `pip install -r requirements.txt`; `web` and `mcp`: `pip install -e ".[test]"`).

## Deploy

Pushes to `main` deploy automatically over SSH with GitHub Actions, one workflow per component (`backend/**`, `web/**`, `mcp/**`, `n8n/**`, `infra/docker-compose.yml`); API, web and MCP run their tests first. `infra/.env` lives only on the server. See [docs/docker.md](docs/docker.md#deploys).

## Documentation

- [Features by module](docs/features.md) — what Alfred does and where to use it
- [Configuration](docs/configuration.md) — environment variables, runtime settings, authentication
- [Docker, volumes and stored files](docs/docker.md) — services, startup, bind mounts, audio and statement files
- [Architecture](docs/architecture.md) — components, request flow, layering, repo tree
- [Data model](docs/data-model.md) — schemas, conventions, tables by module
- [Integrations](docs/integrations.md) — Notion, Google, LLM providers, Telegram
- [Assistant layer](docs/assistant-layer.md) — commands, intents, MCP, Telegram menu
- [Web portal](docs/portal.md) — conventions and pagination pattern
- [Operations](docs/operations.md) — hosting, cron workflows, caller identity
- Modules: [interviews](docs/modules/interviews.md), [metrics](docs/modules/metrics.md), [reminders & overload](docs/modules/reminders-overload.md), [planning](docs/modules/planning.md), [shopping](docs/modules/shopping.md)

Coding rules and conventions for contributors (and for Claude Code) are in [CLAUDE.md](CLAUDE.md).
