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
- Recurring tasks (RRULE-style): completing one advances the deadline to the next cycle; completion history is kept (`/organizer/tasks/{id}/completions`). A misclicked completion can be undone: `DELETE /organizer/tasks/{id}/completions/{completion_id}` removes it and, when it was the latest one, moves the deadline back a cycle (urgency is not restored). The portal offers an **Undo** link on a row that is done for the cycle and a remove button per entry in the History modal.
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

- **Transactions:** add, edit, delete, bulk-move, tags (free-form context such as Travel; entered with a chip input that autocompletes existing tags, flags new names in orange and suggests "Did you mean …?" for near-typos; tags created by an edit are picked up straight away, so they stop showing as new and appear in the tag filter without a reload). The transactions page has a Name search (`search` query param on `GET /finance/transactions`) matching any of the name you gave, the merchant or the raw bank text from the import file, alongside the merchant-only filter. It keeps its filters, sort and page in the query string (updated as you change them, so a refresh or a copied link restores them). A "Clear filters" button appears next to the filters as soon as any is set and resets them all; the tag dropdown has its own "Clear" that unticks just the tags. Tags show as chips on each transaction row (first 3, then "+N tags" with the rest in a tooltip) and in the detail modal. Tag names are case-insensitive everywhere: filters and analytics match "travel" to "Travel", importing or editing with another case reuses the existing tag, and creating or renaming a tag to a name that exists in any case returns 409. Migration 083 seeds the categories Intercity Transport and Accommodation plus a starter set of tags (trips, car, house, utilities, leisure, tech, context); existing names are left alone, transfer linking between accounts, EUR conversion and backfill.
- **Accounts** (the portal list shows each account's current balance, plus limit and available for credit cards), **categories, currencies, tags, recurring transactions** (rules processed on a schedule, `POST /finance/recurring-transactions/process`), **installment plans** (purchases split over months, linked to their transactions). Plans imported from ActivoBank PDFs carry each installment's position, so gaps are detected (`GET /finance/installment-plans/{id}/slots`, `GET /finance/installment-plans/missing`): the portal shows a per-plan slot grid, a "N missing" badge, and a "Statements to import" card grouping missing installments by statement month. *Missing* = a later position is captured; *overdue* = after the last captured one with its month over (may just be unimported). Manually-created plans have no positions and get no slots. `POST /finance/installment-plans/relink` (portal link on the card) links already-imported installment transactions that never joined their plan, matching by account + the `(plan_ref/position)` in the description. Re-importing a statement also heals such rows: a duplicate that matches a plan rule but whose stored transaction is unlinked is shown pre-ticked as "link existing", and committing links it and adds its interest/duty to the plan (`existing_transaction_id` on the preview/commit row, `linked_existing` in the commit response). The installments page shows the interest, duty and total cost of the plans listed.
- **Budgets:** target per category and status per cycle (the cycle start day is a setting). **Tag budgets** (`PUT /finance/budgets/tag-targets/{tag_id}`, `GET /finance/budgets/tag-status`, or `tag_targets` in the bulk `PUT /finance/budgets/targets`) use the same per-cycle versioning on a `budget_targets` row that points at a tag instead of a category (exactly one of `category_id` / `tag_id`). While a tag has an open target, its transactions count toward the tag's budget and are excluded from their category's (uncategorized ones too); a transaction carrying several budgeted tags counts toward the oldest budget only, and `overlap_count` on the tag status reports how many were left out (the portal warns about it on the edit page, the overview and in the tag input). Past cycles are unchanged by a new tag budget (it starts at the current cycle). Deleting a tag with an open budget returns 409. On the edit page only tags that already have a budget are listed; an "Add tag" picker adds any other tag as a row and a small x clears and hides one (applied on Save). The edit, overview and history pages show tag budgets in their own "Tags" group after the categories; the dashboard Remaining card and the insights budget chart include them. The `budget_status` command lists category budgets followed by tag budgets. Targets are versioned per cycle: a change applies from the start of the current cycle, editing again in the same cycle overwrites that version, and a later cycle keeps the earlier version as history (`GET /finance/budgets/history`). The read-only `/finance/budgets/history` portal page shows the last 6 cycles side by side, marking changed budgets. In the portal, the dashboard's Remaining card opens `/finance/budgets/overview` (spent vs. planned per category for a cycle, with month navigation, a budget vs. 12-month-average chart and an "Edit budgets" button); the header's Budgets link and that button open `/finance/budgets`, the edit page, which suggests each category's average EUR spend over the last 12 completed cycles (`GET /finance/budgets/averages`) next to its limit, with a "Use averages" button that fills empty limits without saving.
- **Reports:** spending by category, over time, income vs expense, net worth, averages, top categories, balance forecast, coverage of days with data.
- **Statement import:** upload a file, preview, review, commit. Each supported bank or card format has its own parser (CSV and PDF; list in `app/features/finance/imports/registry.py`). Rules (auto/suggest, amount match) and an embedding + LLM ladder categorise rows; dedup uses the statement's running balance where it has one. The account balance follows the statement too: the latest running balance (checking accounts; the last row of a day wins) or, for the ActivoBank card, the PDF's own "Saldo em Dívida" (stored as the batch's `closing_balance`) plus everything posted after that statement's period end; accounts with neither fall back to summing imported rows dated on/after `opening_balance_date`. Tags can be set for the whole import (`tag_names`) and per row (`tag_names` on each commit row, merged with the batch tags). The original file is kept ([docker.md](docker.md#statement-files-statement_data_dir)).
- **Spending by tag:** the analytics endpoints `report`, `income-report`, `average`, `by-category`, `over-time` and `top` under `/finance/transactions` accept `tags` (repeatable) and `tags_mode=all|any` (default AND). `by-account`, `income-vs-expense-over-time`, `net-worth` and `forecast` ignore them. The insights page has a "By tag" section (tag picker + match all/any) showing the total, a category breakdown, spend over time and the biggest expenses for the chosen tags; the category charts above it stay unscoped.
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

## Travel

Trips with their legs (flights, trains, ...), stays (hotels), an itinerary of planned/visited/missed visits, places with tags and a derived grade, linked card charges with derived costs, trip default finance tags, an import from the local calendar and an after-the-trip recap (spend, what happened, what is still to grade), a day-grouped timeline with maps links, and gap warnings (long wait before check-in, tight connections, overlapping legs). See [modules/travel.md](modules/travel.md).

- **Portal:** `/travel` (filterable trips list), `/travel/{id}`, `/travel/places` (filterable), `/travel/places/{id}`. **Commands:** `travel_trip` / `travel_leg` / `travel_stay` / `travel_place` / `travel_visit` (`/trips`, `/trip`, `/visited` are in the Telegram menu); "what trips do I have coming up" and "show my Rome trip" work in natural language; notes are searchable with `recall`. **API:** `/travel/*`.

## Planning, routines and activities

Claude plans a day or week from Alfred's data; Alfred stores what was agreed. See [modules/planning.md](modules/planning.md).

- **Day plan:** one call returns events, routine steps, travel, tasks, study, language quota, shopping, work totals and the saved plan. Plans are versioned; blocks can be marked done or missed; a weekly review counts what was planned versus done.
- **Routines:** daily-life rhythms, event-based or scheduled, with timed steps. **Activities:** optional gap fillers with a weekly wish and a log.
- **Portal:** `/plan`, `/routines`, `/activities`. **Commands:** `day_plan`, `routine`, `activity`. **API:** `/planning/*`, `/organizer/routines`, `/organizer/activities`.

## Observability

The portal's **Insights** area (`/insights`) is where you see what Alfred has been doing: sessions, messages, memories, working memory, embedding calls, LLM calls (model, feature, tokens), provider (Notion / Google) sync calls, and API/MCP usage per caller. Backed by `/integration/llm-calls`, `/integration/provider-calls`, `/integration/embedding-calls` and `/core/api-requests/summary`.
