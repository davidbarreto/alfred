# Web portal

Conventions for `web/app/`. The portal is a thin client: it fetches from the backend API and renders. Business logic stays in the backend.

## Layout

| File / path | Purpose |
|---|---|
| `web/app/routes/<page>.py` | Route handlers; thin — fetch from backend API, pass to template |
| `web/app/templates/<page>.html` | Full-page Jinja2 templates; always extend `base.html` |
| `web/app/templates/_<partial>.html` | HTMX partial templates; prefixed with `_`; never extend `base.html` |
| `web/app/static/css/portal.css` | Theme variables (light/dark) and the layout classes (see Layout system) |
| `web/app/client.py` | Thin async HTTP wrapper around the backend API (`api.get()`, `api.post()`, ...) |
| `web/app/shared/forward.py` | Proxies portal writes to the backend and relays its error message |
| `web/app/shared/timezone.py` | `local_today()` and friends; same helpers as the backend |

The client sends `X-Alfred-Client: web` on every backend call.

## Layout system

Tailwind and DaisyUI come from a CDN; everything the portal defines itself is in `web/app/static/css/portal.css` (theme variables for light and dark, and the layout classes below). `base.html` links it with `?v={{ static_version }}` (the file's mtime), so a deploy never serves a stale stylesheet. It loads before Tailwind, so a Tailwind utility on the same element wins.

Build pages from these classes instead of ad-hoc grids, so every page lines up the same way on a desktop and on a phone:

| Class | Use |
|---|---|
| `page` | Outer wrapper of every page: gutter (16px phone, 24px from `sm`) and the 80rem maximum width. Add `space-y-4` and, for a narrow page, `max-w-2xl` etc. |
| `page-head` + `page-actions` | Title left, buttons right; the buttons drop under the title when they do not fit |
| `scroll-row` | A line of tabs or chips that can outgrow the screen: scrolls sideways on a phone, wraps from `sm` |
| `stat-row` | Number tiles: two per row on a phone, one line on a desktop |
| `card-row` | Equal cards (charts, previews): as many per row as fit, same height, and a short last row stretches. Narrowest card: `style="--card-min: 16rem"` |
| `card-columns` | Cards of different heights and no popups inside (dashboard): packed in two columns, no holes |
| `split` + `card-stack` | Two independent stacks of cards (trip page, calendar); one column below `lg`. `split-wide-left` makes it 3:2 |
| `filter-bar` | Filters above a list: two-column grid on a phone, wrapping row from `sm`; `filter-wide` spans both columns |
| `action-row` | A list row with text left and its buttons right; the buttons move to their own line when both do not fit. The text is the first child, the buttons the last |
| `chart-box` | Fixed-height box for a Chart.js canvas (`chart-box-lg` for 14rem); the chart needs `maintainAspectRatio: false` |
| `table-scroll` | Wrapper for a table that may be wider than its card; give the table a `min-w-[..]` |

Rules that follow from it:

- **No bare `grid-cols-2`** (or more) for cards: a fixed column count is what squeezes cards on a phone. Use the classes above, or a responsive pair (`grid-cols-1 sm:grid-cols-2`) inside a form.
- **Never give a `<canvas>` a `height` attribute or leave it without a sized parent**: Chart.js then keeps the aspect ratio and the chart grows with the card's width.
- **List rows on a phone**: the title keeps the width; secondary text (location, tags, date column) is hidden below `sm` (`hidden sm:inline`) or moves to the line under the title.
- On a phone no item of a wrapping row is wider than the screen, and any group of controls inside `page-head` wraps: both come from `portal.css`, so a long `<select>` or a row of header buttons needs no per-page fix.
- Controls shown only on hover (`opacity-0 group-hover:opacity-100`) are always visible on touch screens; inputs are 16px on a phone (iOS zooms the page otherwise). Both are handled in `portal.css`.
- A new class name must not collide with a DaisyUI component (`stack`, `join`, `divider`, `steps`, ...): check before adding one.

The sidebar groups its links (Organize, Life, Learning, Assistant); below `md` it is a drawer opened from the top bar, which shows the page title (the `title` block). A new page goes into the fitting group in `base.html`.

Every page is on this system. Two grids are deliberately plain responsive grids, because their tiles should keep one size and stay left-aligned: the task cards and the note cards.

A card that is a link must not contain other links (the browser splits nested `<a>` tags and the card falls apart): make the card a `relative` `<div>`, give the title link `after:absolute after:inset-0`, and put the inner links on `relative z-10` (see `_travel_places_list.html`).

## Interaction rules

HTMX actions target the smallest possible DOM element. Full-page navigation uses standard `<a href>`. Form submissions use `fetch()` + manual DOM update (not `hx-post`) when the response replaces a larger container.

## Capped cards

The trip page's warnings card shows only its title and count, linking to `/travel/{id}/warnings`. Other cards that list things that can grow (calendar events, unlinked charges) show the first 5 and a "See all N" link to a separate page with everything (`/travel/{id}/warnings`, `/travel/{id}/unlinked`), grouped and foldable with `<details>` when there are several groups. Never an in-place expand, even when rows carry their own controls: the full page repeats them (shared row partial and script). Never render an unbounded list on a detail page.

## Pagination pattern

All paginated sections follow the same offset-based pattern:

1. **`limit + 1` trick** — fetch `PAGE_SIZE + 1` items from the API. If the response has more than `PAGE_SIZE` items, there is a next page; slice the list back to `PAGE_SIZE` for rendering.
2. **`_pagination()` helper** — each route module defines:
   ```python
   _PAGE_SIZE = 20  # or appropriate value per page

   def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
       has_next = len(items) > _PAGE_SIZE
       return items[:_PAGE_SIZE], has_next, offset > 0
   ```
3. **HTMX partial routes** — each paginated section has a dedicated `GET /<page>/<section>?offset=N` endpoint that returns only the list partial (not the full page). Prev/Next buttons inside the partial target the section's wrapper `id` with `hx-swap="innerHTML"`.
4. **Variable naming** — use section-namespaced variables to avoid collisions when multiple sections appear on the same page: `memories_offset`, `memories_has_next`, `memories_has_prev`; `wm_offset`, `wm_has_next`, `wm_has_prev`, etc.
5. **Initial page load** — the main page handler fetches a larger batch (e.g. `limit=200`) for stat aggregations and slices the first `PAGE_SIZE` for the initial grid render. Subsequent pages use the HTMX partial route with proper API `offset`.

## Dashboard

`/` fetches every card's data in parallel (`asyncio.gather` over `safe_get`), so one failing module leaves only its own card empty. Card logic lives in `web/app/shared/dashboard.py` (pure functions, unit-tested in `web/tests/test_dashboard.py`); the route only fetches and renders.

| Card | Source |
|---|---|
| Overdue / urgent strip | Counts over the first 200 TODO tasks (`task_alerts`); hidden when both are zero |
| Today's plan | `/planning/saved` for today; the block in progress is marked "now", blocks that already ended are skipped, 5 shown, "See all N" links to `/plan` |
| Current / next trip | `/travel/trips?status=current` (nearest by start date) + the trip's warning count, linking to `/travel/{id}/warnings` |
| Language | `/language/tracks` + `/language/sessions/daily-progress`: today's reviews against each track's quota (no due counts: that needs a call per track) |
| Budgets | `/finance/budgets/status`: the 3 categories closest to their limit |
| Weather | Today's forecast from the structured `/briefing/morning` (no LLM call); empty card when unavailable |
| Today's events | `/organizer/calendar-events` from 14 days back to the end of today, keeping those that overlap today (`todays_events`): multi-day events that started earlier and still run show "Until <date>" instead of a clock range |
| Upcoming events | Events after today within the briefing look-ahead, from `/briefing/morning` (the briefing also looks 14 days back so a running multi-day event counts as today's); 5 max, "See all N" links to the calendar |
| Holidays | Public holidays in the next 7 days, also from `/briefing/morning`, each tagged with its country code (PT, BR) |
| Birthdays | Contacts with a birthday in the next 30 days (computed in the portal; 29 Feb falls on 1 Mar in common years), 5 max |
| Study | Active study plans from `/study/plans/overview`: progress and next open item |
| Metrics | The 4 most-used active series as 14-day sparklines (inline SVG, count series by entries per day, others by daily total) |
| Briefing | The evening digest from 21:30 (until tonight's is saved it falls back to the morning briefing), the morning briefing otherwise. Latest saved one from `/briefing/history` (never generates one: the saved row is text only), clamped to 6 lines |

Every card heading carries a Tabler icon. The morning briefing page keeps only the AI summary; weather, holidays, birthdays, priority tasks, events and pending shopping live on the dashboard.

## Pages

dashboard, tasks (+ `/tasks/insights`), notes, contacts, calendar (+ `/calendar/day/{date}`), shopping (+ `/shopping/insights`), finance, insights, briefing, chat, auth, language, cs, study, metrics (`/metrics`, `/metrics/{name}`), travel (`/travel`, `/travel/{id}`), plan (`/plan`), routines, activities. Feature-specific portal behaviour is documented in the module docs.
