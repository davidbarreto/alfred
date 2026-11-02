# Integrations

External providers live under `backend/app/integrations/<provider>/` (layout in `CLAUDE.md`, Integration module layout). This file is the inventory and the quirks worth knowing before touching one.

## Inventory

| Provider | Role | Notes |
|---|---|---|
| **Notion** | Store for tasks and notes | Write-through cache: Alfred DB is the read layer, Notion the external store. `NotionStorageProvider` forwards every non-null record key to Notion. |
| **Google Calendar** | Store for calendar events | Write-through via `StorageProvider`; OAuth token in the `oauth_tokens` table; `sync()` pulls changes back in. |
| **Google Contacts** | Store for contacts | Write-through via `StorageProvider`; full CRUD scope (`contacts`); also one-way sync via `/integration/google-contacts/sync`. |
| **Google (Gemini)** | LLM provider | Chat, memory extraction, briefing formatting, session summaries, language pronunciation analysis (`gemini-2.5-flash` for audio). |
| **OpenAI** | LLM provider | Alternative `LlmProvider` implementation. |
| **sentence-transformers** | Embedding provider | Local; feeds `core.embeddings`. |
| **Open-Meteo** | Weather | Morning briefing and metrics weather snapshots; no API key required. |
| **Telegram** | Input channel | **Only via n8n.** Never call the Telegram API directly from FastAPI. Command menu limits: [assistant-layer.md](assistant-layer.md#telegram-command-menu). |
| **Codeforces / LeetCode** | Programming-practice sync | Feeds the `cs` schema. |

Supporting modules: `oauth_tokens/` (generic OAuth refresh-token store), `llm_calls/` (every LLM call is logged), `provider_calls/` (integration sync log), `http/` (shared pagination helpers).

## Quirks

- **Alfred-only fields never go to the provider.** `TaskService` strips `_ALFRED_ONLY_FIELDS` before every Notion call and skips the call entirely when an update touches only those fields. `CalendarEventService` does the same for Google, and `sync()` never writes them. Event `tags` are Alfred-only too, so a tags-only update works without OAuth. Full list: [modules/planning.md](modules/planning.md#alfred-only-fields).
- **Skipping an occurrence is Alfred-only; moving or ending one is written through to Google.** See [modules/planning.md](modules/planning.md#skipping-moving-and-ending-recurring-events). The instance-id format and the exception write are untested against real Google.
- **Google modified instances** (`recurringEventId` + `originalStartTime`) become overrides of their series during `sync()`, not standalone events.
- **Weather is best-effort.** `ConditionsProvider.get_current_conditions` has a 4 s timeout and must never block the caller.
- **Domain conflicts become 409** through one handler in `app/main.py` (shopping errors, for example), so they are warnings, not errors, in Telegram/MCP logs.
