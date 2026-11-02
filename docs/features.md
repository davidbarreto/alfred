# Features by module

What Alfred can do, module by module, and where to do it. Every module is reachable through up to four surfaces:

- **Portal**: the pages in the web UI (left navigation).
- **Telegram / chat**: slash commands and natural language (typed or voice). `/help` lists the commands and `/help <command>` shows the arguments.
- **MCP**: the same commands as `alfred_<group>` tools in Claude (the `action` is the second word of the command).
- **API**: the backend routes under the prefix shown (Swagger UI at `/docs` on the backend).

Design details and rules per module are in `docs/modules/` where a module doc exists.

## Tasks

Todo items with status, priority, deadline, tags and recurrence, stored in Notion and mirrored in Alfred (write-through).

- Create, list, search, update, complete, cancel, delete; "pending" shows overdue and today's tasks.
- Priority and **urgency**: overdue or long-undated tasks escalate to URGENT automatically; **snooze** silences the no-deadline reminder for one task.
- Recurring tasks (RRULE-style): completing one advances the deadline to the next cycle; completion history is kept (`/organizer/tasks/{id}/completions`).
- Planning fields: `estimate_minutes`, `context`, `available_from` (Alfred-only, never sent to Notion).
- **Portal:** `/tasks` (list with history), `/tasks/insights` (charts, overload section and settings).
- **Commands:** `task` add / list / search / pending / update / complete / cancel / snooze / delete.
- **API:** `/organizer/tasks`.
- See [modules/reminders-overload.md](modules/reminders-overload.md) for reminders, escalation, overload and the catch-up plan.

## Notes

Free-text notes with title, tags and links, stored in Notion and mirrored.

- Add, search, list, get, update, delete, **archive / unarchive**.
- **Portal:** `/notes` (grid) and `/notes/archived`.
- **Commands:** `note` add / search / list / get / update / delete. **API:** `/organizer/notes`.

## Calendar

Events mirrored from and written through to Google Calendar (OAuth, one-time connect).

- Create, list (default next 14 days), update, delete; all-day and timed events, locations, recurrence.
- **Recurring events:** skip or restore one occurrence, move one occurrence to another time, end a series. Skips are Alfred-only; moves and ends are written to Google ([modules/planning.md](modules/planning.md#skipping-moving-and-ending-recurring-events)).
- Planning fields per event: `availability`, `presence`, `travel_minutes`, attached routine.
- **Notifications:** events notify at configurable offsets per profile (`/organizer/calendar-notification-settings`); the n8n workflow polls `/organizer/calendar-notifications/due`.
- **Sync:** `POST /integration/google-calendar/sync` pulls changes from Google, including moved instances.
- **Portal:** `/calendar` and `/calendar/day/{date}` (day view with skip/move/end actions).
- **Commands:** `event` add / list / update / skip / unskip / reschedule / unreschedule / endseries / delete. **API:** `/organizer/calendar-events`.

## Contacts

Write-through cache of Google Contacts with full CRUD.

- List, search, get, create, update, delete; relationship filter (family, relative, friend, other).
- **Birthdays:** notifications and the morning briefing use contact birthdays; timing is set in `/organizer/contact-birthday-settings`.
- **Portal:** `/contacts`. **Commands:** `contact` list / search / get. **API:** `/organizer/contacts`; sync with `POST /integration/google-contacts/sync`.

## Shopping and wishlist

Shopping list with a product catalog, wishlist, and recurring items. Full rules: [modules/shopping.md](modules/shopping.md).

- Add by name (finds or creates the product), mark bought or skipped, categories, quantities and units, stores, priorities.
- One pending entry per product; frequent-item quick-add chips; merge duplicate products.
- Wishlist items can be promoted to the list. Recurrence items suggest what is due and are accepted into the list.
- **Insights:** by category, by month, by store, priority split, and how often you buy each product.
- **Portal:** `/shopping` (list, wishlist, recurring, products, categories) and `/shopping/insights`.
- **Commands:** `shopping` add / list / complete / delete / update; `wishlist` add / list / delete / promote. **API:** `/organizer/shopping`, `/wishlist`, `/recurrence`, `/shopping-products`, `/shopping-categories`.

## Memories, working memory and recall

Alfred's long-term knowledge about you and the short-term context it carries.

- **Memories** have a category (`fact`, `preference`, `relationship`, `skill`, `episodic`, `goal`) and an importance. They are created two ways: **automatically** (an LLM extracts them from your chats and de-duplicates by embedding similarity, bumping the importance of near-duplicates) and **manually** through the API. Each memory is embedded so it can be found by meaning.
- **Manage:** list and delete in the portal at `/insights/memories`; create and edit (`POST`, `PATCH`) through `/core/memories`. Telegram/MCP can **list**, **search** (keyword) and **recall** (semantic search). There is no add command; tell Alfred in chat (extraction picks it up) or POST to the API.
- **Working memory** holds short-lived context items (a `key`, its content, an optional `expires_at`), for example the CS weak spots loaded for the next few hours. List and delete them at `/insights/working-memory`, via the `working_memory` list command, or `/core/working-memory`.
- **Embeddings** (`/core/embeddings`) are a derived index of memories and other sources; `POST /core/embeddings/backfill` rebuilds missing ones. Inspect calls in the portal at `/insights/embeddings`.

## Chat and assistant

- **Chat:** `/chat` in the portal, or Telegram. Messages are classified into a command (embedding match, LLM fallback) and executed; anything else is a normal conversation with the LLM.
- **Voice:** Telegram voice messages are transcribed (`POST /core/transcription`) and handled like text.
- **Commands:** `assistant focus` ("what should I focus on now"), `reminder set`, `weather current`, `recall search`, `help`.
- **Sessions and messages:** every conversation is logged (`/core/sessions`, `/core/messages`, `/core/command-executions`); browse them in the portal under `/insights`.

## Briefings and monitoring

- **Morning briefing:** weather, today's tasks and events, upcoming birthdays and holidays, language review due, formatted by the LLM. Evening digest is the counterpart. Both run from n8n crons; `/briefing` in the portal shows today's and the history (`/briefing/history`).
- **Watchers:** monitors of type static HTML page, JavaScript-rendered HTML page, or API, checked on a schedule by an n8n workflow; results are stored as executions and alerts. Manage them in the portal at `/watcher`; commands `watcher` list / get and `alert` list; API `/watcher/configs`, `/watcher/alerts`, `/watcher/executions`.
- **Pause:** a global switch that stops reminders and briefings and freezes urgency escalation; resuming restores it ([configuration.md](configuration.md#2-settings-you-change-at-runtime)).

## Finance

Multi-account, multi-currency ledger with budgets, reports and statement imports.

- **Transactions:** add, edit, delete, bulk-move, tags (free-form context such as Travel), transfer linking between accounts, EUR conversion and backfill.
- **Accounts, categories, currencies, tags, recurring transactions** (rules processed on a schedule, `POST /finance/recurring-transactions/process`), **installment plans** (purchases split over months, linked to their transactions).
- **Budgets:** monthly target per category and status per cycle (the cycle start day is a setting).
- **Reports:** spending by category, over time, income vs expense, net worth, averages, top categories, balance forecast, coverage of days with data.
- **Statement import:** upload a file, preview, review, commit. Each supported bank or card format has its own parser (CSV and PDF; list in `app/features/finance/imports/registry.py`). Rules (auto/suggest, amount match) and an embedding + LLM ladder categorise rows; dedup uses the statement's running balance where it has one. The original file is kept ([docker.md](docker.md#statement-files-statement_data_dir)).
- **Portal:** `/finance` and sub-pages for transactions, accounts, budgets, import (with rules and batches), installments, coverage, insights and settings.
- **Commands:** `finance` (transaction add / list / update / delete, budget set, spending report / average / top, budget status, balance forecast), `account`, `category`, `recurring` (read-only). **API:** `/finance/*`.

## Language learning

Per-language tracks with CEFR level, a daily quota and a review mode.

- **Chunks:** vocabulary and phrases with FSRS-5 spaced-repetition state, tags, approval triage, and a Pareto-weighted daily batch. Seeds for six languages are loaded on deploy.
- **Grammar scope:** per-track curriculum, each item active / deferred / mastered.
- **Sessions:** SRS **review**, **shadowing** (record yourself, get pronunciation feedback), **production** (sentence, translate, journal, timed writing, spoken speak/retell, graded by the LLM), and free-form **conversation** or **roleplay** with spoken replies.
- **Pronunciation:** text-to-speech audio per phrase, cached on disk.
- **Portal:** `/languages` (tracks, chunks, tags, triage, review, shadow, produce, sessions, chats, grammar scope, insights).
- **Commands:** `language` practice / review / produce / conversation / conversation_roleplay / stop; `track` list; `grammar_scope` list. **API:** `/language/*`.

## CS practice and study planner

- **CS coach:** syncs Codeforces and LeetCode submissions, tracks weak tags and streaks, recommends problems. Portal `/cs`; command `cs context` loads weak spots into working memory; API `/cs/*`.
- **Study planner:** tracks, LLM-generated plans with a backlog and a cap on active plans, items you complete. Portal `/study`; command `study plans`; API `/study/*`. Design: `docs/plans/study-coach.md`.

## Interview prep and tracking

- **Prep** ([modules/interviews.md](modules/interviews.md)): STAR stories with a strength score, behavioral questions linked to stories with a fit score, candidate questions to ask, a shared tag vocabulary, and an AI strength suggestion.
- **Tracking:** companies, interview processes (can be extracted from a job-posting URL), stages with linked contacts, tasks and notes, links, insights, and your search preferences.
- **Portal:** `/interviews` (processes, companies, preferences) and `/interview-prep` (stories, questions, candidate questions).
- **Commands:** `interview`, `interview_story`, `interview_prep`, `interview_candidate`. **API:** `/organizer/interview-*`, `/organizer/candidate-questions`.

## Metrics

Personal measurement log: timed things (commute), values (weight) and counts (coffee), with weather snapshots and stats by tag, hour, weekday and weather. See [modules/metrics.md](modules/metrics.md).

- **Portal:** `/metrics`. **Commands:** `metric` start / stop / log / open / history / discard. **API:** `/metrics/*` (including `/metrics/quick/*` for Shortcuts).

## Planning, routines and activities

Claude plans a day or week from Alfred's data; Alfred stores what was agreed. See [modules/planning.md](modules/planning.md).

- **Day plan:** one call returns events, routine steps, travel, tasks, study, language quota, shopping, work totals and the saved plan. Plans are versioned; blocks can be marked done or missed; a weekly review counts what was planned versus done.
- **Routines:** daily-life rhythms, event-based or scheduled, with timed steps. **Activities:** optional gap fillers with a weekly wish and a log.
- **Portal:** `/plan`, `/routines`, `/activities`. **Commands:** `day_plan`, `routine`, `activity`. **API:** `/planning/*`, `/organizer/routines`, `/organizer/activities`.

## Observability

The portal's **Insights** area (`/insights`) is where you see what Alfred has been doing: sessions, messages, memories, working memory, embedding calls, LLM calls (model, feature, tokens), provider (Notion / Google) sync calls, and API/MCP usage per caller. Backed by `/integration/llm-calls`, `/integration/provider-calls`, `/integration/embedding-calls` and `/core/api-requests/summary`.
