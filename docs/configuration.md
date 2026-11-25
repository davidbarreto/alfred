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
| `HOLIDAY_CALENDARS` | Optional. Comma-separated `CODE=google_calendar_id` pairs for the public holidays shown on the dashboard and in the briefing (the code is the badge shown next to each holiday). Unset or empty uses Portugal and Brazil. The **first** entry is the planning calendar: only its holidays appear in the day plan and switch locations to their holiday opening hours. A malformed entry stops the backend at startup |
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

`URGENCY_RESET_DAYS` (default 7) and `UNDATED_TASK_SNOOZE_DAYS` (default 7) are only fallbacks: the runtime settings `reminders.urgency_reset_days` and `reminders.undated_task_snooze_days` (below) win when they are set. The rest of the reminder tuning is a runtime setting too.

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
| **Reminders & overload** (`reminders.*` in `core.settings`) | Escalation grace periods, undated-task age, re-remind cadence, overload thresholds, max tasks listed, catch-up tuning, urgency reset days, reminder look-aheads (`task_lookahead_hours` 24, `event_lookahead_hours` 2), how long a snoozed undated task stays out of escalation (`undated_task_snooze_days`) | Portal: `/settings#reminders`. API: `GET/PUT /core/reminder-settings` |
| **Travel settings** (`travel.*`) | `airport_buffer_min` (default 120): how long before departure to be at the airport; `home_to_airport_min` (default 45): the ride there. Together they give the leave-home time and its reminder; the home address (read-only here: it is the Home location's address, edited on `/locations`; `PUT` refuses it) is where the home → airport directions start; `home_city_id` (optional, a `travel.cities` id; empty = none) is the city trips start from, and changing it (or the address or either time) first copies the old value into every trip that has already started and has none of its own (see `modules/travel.md`, *Home*). Also: `leave_home_lead_min` (60, when the "time to leave" reminder goes out), `check_in_opens_hours` (24), `tight_connection_min` (90), `long_wait_hours` (4), `checklist_nudge_days` (60), `rain_mm` (2.0, a rainy trip day), `charge_link_lead_days` / `charge_link_tail_days` (90 / 30, the window for charges carrying a trip's tags), plus `max_visits_per_day`, `visit_duration_min`, `unpaid_leg_days` and `snooze_other_events` | Portal: `/settings#travel`. API: `GET/PUT /travel/settings` |
| **Briefing** (`briefing.*`) | `lookahead_days` (default 3: the days the morning briefing covers, today included; also the dashboard's upcoming events), `holiday_lookahead_days` (7), and how many items each morning briefing section spells out before "+N more": tasks today 8, upcoming tasks 4, events today 8, upcoming events 4, shopping items 6, recurring purchases 5 | Portal: `/settings#briefing`. API: `GET/PUT /briefing/settings` |
| **Language** (`language.*`) | `requested_retention` (0.70-0.97, default 0.9: only intervals from the next review on change), `leech_threshold` (8), `timed_task_seconds` (300) | Portal: `/settings#language`. API: `GET/PUT /language/settings` |
| **Persona** (`assistant.*`) | `user_name` (how prompts name the user: the chat and the morning and evening briefings; empty = "the user") and `persona_additions` (markdown added after the committed basic persona `backend/app/assistant/persona.md`; personal, so it lives only in the database) | Portal: the name on `/settings#assistant`, the additions on `/persona`. API: `GET/PUT /core/assistant-settings` |
| **Global pause** | Stops reminders and briefings and freezes task urgency escalation until resumed | Portal: pause control; Telegram/MCP: `/pause`, resume with the `pause stop` action. API: `POST /core/pause`, `POST /core/pause/resume`, history at `GET /core/pause/history` |
| **Weather place** (`weather.*`) | `location_id` (a location with coordinates) or `city_id` (a travel city, geocoded by name), at most one (both is a 422; a location without coordinates or archived is a 422, an unknown one a 404). Both empty = the Home location. Used by the morning briefing, the dashboard, the `weather` command without a place and the metrics snapshots without device coordinates. Resolution: the chosen location's coordinates, the chosen city, the Home location's coordinates, else no weather (the briefing and the dashboard say how to set one). A chosen location that is later deleted or archived falls back to Home with a WARNING log | Portal: `/settings#weather`. API: `GET/PUT /core/weather-settings` (the GET also lists the choices and the place in use) |
| **Planning preferences** (`planning.*`) | Wake/sleep time, work target, preferred work windows, workdays, work/office tags, office days per week and minimum minutes, free-text conventions, what the day plan lists and assumes (`backlog_stale_days` 60, `due_lookahead_days` 3, `assumed_estimate_minutes` 30, `shopping_run_minutes` 45, `study_items_per_plan` 5), travel times (stored as rows between locations, also editable on each location's page) | Portal: `/settings#planning` (travel times on each location's page). MCP/Telegram: `day_plan settings` / `set_settings`. API: `GET/PUT /planning/settings` |
| **Finance settings** | `cycle_start_day` (1-28): the day your monthly finance cycle starts. Budget targets per category are separate | Portal: `/settings#finance` (`/finance/settings` redirects there), budget targets on `/finance/budgets`. API: `GET/PUT /finance/settings`, `/finance/budgets/targets` |
| **Study settings** | `max_active_plans` (1-10): the global cap on active study plans | Portal: `/settings#study`. API: `GET/PUT /study/settings` |
| **Calendar notifications** | The reminder offsets (a cascade) for each notification profile (`cant_miss`, `important`, `normal`, `light`, `aware`); `normal` is the default. An unknown profile is a 422 | Portal: `/settings#organizer` (JSON editor). API: `GET /organizer/calendar-notification-settings`, `PUT .../{profile}` |
| **Contact birthday notifications** | `birthday_lookahead_days` (7, the briefing; family and relatives at least 30) and `birthday_dashboard_days` (30), `PUT /organizer/contact-birthday-settings`; the birthday offsets per relationship (`family`, `relative`, `friend`, `other`). An unknown relationship is a 422 | Portal: `/settings#organizer` (JSON editor). API: `GET /organizer/contact-birthday-settings`, `PUT .../{relationship}` |
| **Interview preferences** | Work regimes, target office days per month, salary range and currency, locations, tech stack, roles, career objectives | Portal: `/interviews/preferences`. API: `GET/PATCH /organizer/interview-preferences` |
| **Language tracks** | Per track: language code, CEFR level, daily quota, review mode, pause/resume | Portal: `/languages`. API: `/language/tracks` |
| **Telegram command menu** | Which commands appear in Telegram's `/` menu | `_MENU_COMMANDS` in code; apply with `POST /integration/telegram/set-commands`. See [assistant-layer.md](assistant-layer.md#telegram-command-menu) |

Every `core.settings` value above is edited on the portal's `/settings` page (see [portal.md](portal.md#settings-page)); interview preferences, language tracks and budget targets keep their own pages.

### The settings catalog

`GET /core/settings/catalog` lists every `core.settings` field above (planning, reminders, travel, finance, study, the organizer cascades, assistant) with its label, hint, control (`widget`), type, limits, unit, fieldset (`group`), default and the routes that read and write it, plus `unregistered`: the stored keys no field covers (checklist template, pause state), with their values. `assistant.*` keys never appear there. It holds no values of its own: each namespace is still read and written through its own GET and PUT, so its validation and side effects always run.

The catalog is built from the settings schemas, not a separate registry: each `Update` schema field is declared with `setting(...)` (`app/features/core/settings/metadata.py`: title, description, widget, unit, group, `confirm_note`), and the defaults come from each feature's `DEFAULTS`. A new settings field shows up by being declared; one without a title fails `tests/test_settings_catalog.py`. A new namespace is one entry in `NAMESPACES` (`app/features/core/settings/catalog.py`).

## 3. Authentication

| Entry point | How it authenticates |
|---|---|
| Backend API | `Authorization: Bearer <ALFRED_API_TOKEN>` on every route (router-level `require_auth`). Callers also send `X-Alfred-Client` |
| Web portal | Password login (`WEB_PASSWORD`), signed session cookie (`SESSION_SECRET_KEY`). The portal itself calls the backend with the API token |
| MCP server | OAuth 2.1 with Dynamic Client Registration; the login page uses `MCP_LOGIN_PASSWORD`. Registered clients persist in `MCP_DATA_DIR` |
| Telegram | n8n receives the messages; the bot token stays in n8n/`.env` |
| Google Calendar / Contacts | One-time browser OAuth: open `GET /integration/google-calendar/oauth/url` (and the contacts equivalent), approve, and the callback stores a refresh token in `oauth_tokens`. `GET .../status` shows whether it is connected |
