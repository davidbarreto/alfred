# Configuration

Alfred has three layers of configuration:

1. **Environment variables** (`infra/.env`, read by `backend/app/config.py` and the other services) for secrets, URLs, models and file locations. Changing them needs a container restart.
2. **Settings stored in the database** (`core.settings` and a few dedicated tables) that you change at runtime from the portal, Telegram/MCP or the API.
3. **Authentication** for each entry point.

`infra/.env.example` is the template; copy it to `infra/.env` and fill it in. `.env` is gitignored.

## 1. Environment variables

Values below are the defaults from `Settings` when the variable is optional. **Required** means the backend will not start without it.

### Core

| Variable | Purpose |
|---|---|
| `ENV` | `local` or `production` |
| `LOG_LEVEL` | `INFO` or `DEBUG` |
| `TIMEZONE` | IANA zone used for every "today", day boundary and n8n schedule (default set in `Settings.timezone`). Changing it needs no data migration |
| `SESSION_EXPIRY_HOURS` | How long a chat session stays reusable after its last message (default 4) |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `BACKEND_PORT`, `BACKEND_HOST`, `WEB_PORT`, `MCP_PORT`, `N8N_PORT` | Host ports (loopback) |

### Database

| Variable | Purpose |
|---|---|
| `DATABASE_URL` (**required**) | Connection used by the app (restricted role, `postgresql+asyncpg://...`) |
| `DATABASE_ADMIN_URL` | Connection used by Alembic migrations (schema owner) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_ADMIN_USER`, `DB_ADMIN_PASSWORD` | Create the database and roles on first start |
| `N8N_DB_NAME`, `N8N_DB_USER`, `N8N_DB_PASSWORD`, `N8N_DB_HOST`, `N8N_DB_PORT` | n8n's own database |
| `VECTOR_EXTENSION` | Vector extension name (pgvector) |

### Storage locations

`DB_DATA_DIR`, `N8N_DATA_DIR`, `STATEMENT_DATA_DIR`, `AUDIO_DATA_DIR`, `HF_CACHE_DIR`, `MCP_DATA_DIR` are host folders; `STATEMENT_STORAGE_DIR` and `AUDIO_STORAGE_DIR` are the matching container paths (defaults `/data/statements`, `/data/audio`). Details: [docker.md](docker.md#volumes-data-that-lives-on-the-host).

### Integrations

| Variable | Purpose |
|---|---|
| `NOTION_API_KEY`, `NOTION_TASKS_DATABASE_ID`, `NOTION_NOTES_DATABASE_ID` (**required**) | Notion store for tasks and notes. `NOTION_BASE_URL` and `NOTION_API_VERSION` have defaults |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_CALENDAR_OAUTH_REDIRECT_URI` (**required**) | One Google OAuth client shared by Calendar and Contacts |
| `GOOGLE_CONTACTS_OAUTH_REDIRECT_URI` | Contacts callback (default `http://localhost:8000/integration/google-contacts/oauth/callback`) |
| `GOOGLE_CALENDAR_ID` | Calendar to sync (default `primary`) |
| `GEMINI_API_KEY` | Gemini key for chat, extraction, transcription, pronunciation and TTS. Optional to boot, but chat and language features need it |
| `GCP_API_KEY` | Separate Google Cloud key (public holidays API) |
| `OPENAI_API_KEY` | Optional alternative LLM provider |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Used by n8n to talk to Telegram; the backend only uses the token to register the command menu |
| `LEETCODE_SESSION`, `LEETCODE_CSRF_TOKEN` | Copied from a logged-in browser session for the CS coach sync. They expire; renew them in `.env` when sync starts failing |

### Models and intent detection

| Variable | Default |
|---|---|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |
| `LLM_CHAT_MODEL`, `LLM_CHAT_TEMPERATURE` | `gemini-2.0-flash`, `0.35` |
| `LLM_EXTRACTION_MODEL` | `gemini-2.5-flash-lite` |
| `LLM_PRONUNCIATION_MODEL`, `LLM_TRANSCRIPTION_MODEL`, `LLM_CONVERSATION_MODEL` | `gemini-2.5-flash` |
| `LLM_CONVERSATION_TTS_MODEL`, `CONVERSATION_TTS_VOICE` | `gemini-2.5-flash-tts`, `Enceladus` |
| `INTENT_THRESHOLD` | `0.7`: embedding score at or above this picks the intent directly |
| `INTENT_SHORTLIST_FLOOR`, `INTENT_SHORTLIST_K` | `0.4`, `5`: between the floor and the threshold the top K intents are shortlisted for an LLM to classify; below the floor the message falls through to chat |
| `PERSIST_CONVERSATION_AUDIO` | `false` |

### Reminders

`UNDATED_TASK_SNOOZE_DAYS` (default 7) and `URGENCY_RESET_DAYS` (default 7, can also be set in the portal) are env-only defaults. The rest of the reminder tuning is a runtime setting (below).

### Web portal and MCP

| Variable | Purpose |
|---|---|
| `WEB_PASSWORD`, `SESSION_SECRET_KEY` | Portal login and cookie signing |
| `PUBLIC_BACKEND_URL` | Backend URL as seen by the browser |
| `MCP_PUBLIC_URL`, `MCP_LOGIN_PASSWORD`, `MCP_SESSION_SECRET_KEY` | MCP server public URL and OAuth login |

### n8n

`N8N_HOST`, `N8N_PROTOCOL`, `WEBHOOK_URL`, `N8N_EDITOR_BASE_URL`, `NODE_ENV`, `N8N_ENCRYPTION_KEY` (do not lose it: it encrypts stored credentials), and `N8N_OWNER_EMAIL`, `N8N_OWNER_PASSWORD`, `N8N_OWNER_FIRST_NAME`, `N8N_OWNER_LAST_NAME` (used by `setup_n8n.sh` to create the owner).

### Test and CI only

`DISABLE_INTEGRATIONS=true` swaps the LLM and Notion providers for null implementations so the API boots without real credentials (used by the CI smoke test).

## 2. Settings you change at runtime

Stored in the database, so no restart or redeploy. Where each one lives:

| Setting | What it controls | Where to change it |
|---|---|---|
| **Reminders & overload** (`reminders.*` in `core.settings`) | Escalation grace periods, undated-task age, re-remind cadence, overload thresholds, max tasks listed, catch-up tuning, urgency reset days | Portal: Overload section of `/tasks/insights`. API: `GET/PUT /core/reminder-settings` |
| **Travel settings** (`travel.*`) | `airport_buffer_min` (default 120): how long before departure to be at the airport; `home_to_airport_min` (default 45): the ride there. Together they give the leave-home time and its reminder; `organizer.home_address` (optional text; personal data, so it lives in the organizer namespace and is edited with the other travel settings) is where the home → airport directions start | Portal: Reminder settings on `/travel`. API: `GET/PUT /travel/settings` |
| **Global pause** | Stops reminders and briefings and freezes task urgency escalation until resumed | Portal: pause control; Telegram/MCP: `/pause`, resume with the `pause stop` action. API: `POST /core/pause`, `POST /core/pause/resume`, history at `GET /core/pause/history` |
| **Planning preferences** (`planning.*`) | Wake/sleep time, work target, preferred work windows, workdays, work/office tags, office days per week and minimum minutes, free-text conventions, travel times | Portal: `/plan`. MCP/Telegram: `day_plan settings` / `set_settings`. API: `GET/PUT /planning/settings` |
| **Finance settings** | `cycle_start_day` (1-28): the day your monthly finance cycle starts. Budget targets per category are separate | Portal: `/finance/settings`, `/finance/budgets`. API: `GET/PUT /finance/settings`, `/finance/budgets/targets` |
| **Study settings** | `max_active_plans` (1-10): the global cap on active study plans | API: `GET/PUT /study/settings` |
| **Calendar notifications** | The reminder offsets (a cascade) for each notification profile; `normal` is the default | API: `GET /organizer/calendar-notification-settings`, `PUT .../{profile}` |
| **Contact birthday notifications** | Birthday notification timing | API: `GET/PUT /organizer/contact-birthday-settings` |
| **Interview preferences** | Work regimes, target office days per month, salary range and currency, locations, tech stack, roles, career objectives | Portal: `/interviews/preferences`. API: `GET/PATCH /organizer/interview-preferences` |
| **Language tracks** | Per track: language code, CEFR level, daily quota, review mode, pause/resume | Portal: `/languages`. API: `/language/tracks` |
| **Telegram command menu** | Which commands appear in Telegram's `/` menu | `_MENU_COMMANDS` in code; apply with `POST /integration/telegram/set-commands`. See [assistant-layer.md](assistant-layer.md#telegram-command-menu) |

Settings that have no portal form (study, calendar notifications, birthdays) are changed through the API (Swagger UI at `/docs` of the backend) or MCP.

## 3. Authentication

| Entry point | How it authenticates |
|---|---|
| Backend API | `Authorization: Bearer <ALFRED_API_TOKEN>` on every route (router-level `require_auth`). Callers also send `X-Alfred-Client` |
| Web portal | Password login (`WEB_PASSWORD`), signed session cookie (`SESSION_SECRET_KEY`). The portal itself calls the backend with the API token |
| MCP server | OAuth 2.1 with Dynamic Client Registration; the login page uses `MCP_LOGIN_PASSWORD`. Registered clients persist in `MCP_DATA_DIR` |
| Telegram | n8n receives the messages; the bot token stays in n8n/`.env` |
| Google Calendar / Contacts | One-time browser OAuth: open `GET /integration/google-calendar/oauth/url` (and the contacts equivalent), approve, and the callback stores a refresh token in `oauth_tokens`. `GET .../status` shows whether it is connected |
