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

Dark mode remaps Tailwind's light gray and tint classes in `portal.css` (`html[data-theme="dark"] .bg-gray-50 { ... }`). An opacity variant such as `bg-gray-50/60` is a separate class that those overrides miss, so it paints the light colour over a dark card: give each variant a template uses its own dark override (a test in `web/tests/test_dashboard.py` checks the gray ones), or prefer a token-based class. The calendar does the latter: `cal-empty`, `cal-today`, `cal-day` (hover), `cal-holiday` and `cal-holiday-text` read `--cal-*` tokens defined for both themes; holidays are a soft red, pinker than the error red.

Build pages from these classes instead of ad-hoc grids, so every page lines up the same way on a desktop and on a phone:

| Class | Use |
|---|---|
| `page` | Outer wrapper of every page: gutter (16px phone, 24px from `sm`) and the 80rem maximum width. Add `space-y-4` and, for a narrow page, `max-w-2xl` etc. |
| `page-head` + `page-actions` | Title left, buttons right; the buttons drop under the title when they do not fit |
| `scroll-row` | A line of tabs or chips that can outgrow the screen: scrolls sideways on a phone, wraps from `sm` |
| `stat-row` | Number tiles: two per row on a phone, one line on a desktop |
| `card-row` | Equal cards (charts, previews): as many per row as fit, same height, and a short last row stretches. Narrowest card: `style="--card-min: 16rem"` |
| `card-grid` | Cards of one width (city, country, everyday place cards): as many columns as fit, and a short last row keeps the same card width; one full-width column on a phone. Same `--card-min` |
| `card-columns` | Cards of different heights and no popups inside (dashboard): packed in two columns, no holes |
| `split` + `card-stack` | Two independent stacks of cards (trip page, calendar); one column below `lg`. `split-wide-left` makes it 3:2 |
| `filter-bar` | Filters above a list: two-column grid on a phone, wrapping row from `sm`; `filter-wide` spans both columns |
| `settings-layout` + `side-nav` | A page with a section index (`/settings`): from `lg` a sticky side navigation left of the section cards; below `lg` the nav is hidden and the page shows the same links as a `scroll-row` of chips |
| `action-row` | A list row with text left and its buttons right; the buttons move to their own line when both do not fit. The text is the first child, the buttons the last |
| `chart-box` | Fixed-height box for a Chart.js canvas (`chart-box-lg` for 14rem); the chart needs `maintainAspectRatio: false` |
| `table-scroll` | Wrapper for a table that may be wider than its card; give the table a `min-w-[..]` |
| `cover-box` (+ `cover-hero`, `cover-shade`, `cover-badge`, `cover-credit`, `cover-mosaic`) | A cover photo at a fixed ratio (16:9 cards; `cover-hero` is a full-width banner with a capped height), cropped with `object-fit: cover`, a gradient placeholder without an image, the title over a dark gradient (`cover-shade`), a corner badge and photo credit, or a 2x2 mosaic of covers. Load card images with `loading="lazy"` and a `?v=<updated_at>` cache key (city and country pages) |
| `places-map` (+ `places-map-card`, `pm-legend`) | The Leaflet map of `places-map.js`: 2:1 on a desktop, taller on a phone (`places-map-card` is the fixed 18rem card on a city or country page). Set `data-map-data` (the `/places/map/data` URL) and `data-fit` (`world`, `country`, `city`), and include `_places_map_assets.html` once. Layer and status toggles are page checkboxes (`data-map-toggle`, `data-map-status`, the latter from `_places_map_toggles.html`). The country shapes in `static/js/world.json` are Natural Earth (public domain), rebuilt with `web/scripts/build_world_map.py` ([modules/places.md](modules/places.md#map)) |

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

## Numbers link to their source

A count or total on a page (a stat tile, "3 nights", "5 legs", a spend figure, a counter) links to the list it was counted from: the trips, the stays, the legs, the transactions behind a spend. When that list has no page yet, add one (paginated, see *Capped cards*) rather than leave the number plain. The exception is a number inside an element that is already a link (a cover card that opens its page): no nested links, so it stays plain and the page it opens has the linked version.

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
| Weather | Today's forecast from the structured `/briefing/morning` (no LLM call), with the place it was looked up at (`weather_place`); when there is no weather place the card shows `weather_note` with a link to `/settings#weather` |
| Today's events | `/organizer/calendar-events` from 14 days back to the end of today, keeping those that overlap today (`todays_events`): multi-day events that started earlier and still run show "Until <date>" instead of a clock range |
| Upcoming events | Events after today within the briefing look-ahead, from `/briefing/morning` (the briefing also looks 14 days back so a running multi-day event counts as today's); 5 max, "See all N" links to the calendar |
| Holidays | Public holidays in the next `briefing.holiday_lookahead_days` (default 7), also from `/briefing/morning`, each tagged with its country code (PT, BR) |
| Birthdays | Contacts with a birthday in the next 30 days (computed in the portal; 29 Feb falls on 1 Mar in common years), 5 max |
| Study | Active study plans from `/study/plans/overview`: progress and next open item |
| Metrics | The 4 most-used active series as 14-day sparklines (inline SVG, count series by entries per day, others by daily total) |
| Briefing | The evening digest from 21:30 (until tonight's is saved it falls back to the morning briefing), the morning briefing otherwise. Latest saved one from `/briefing/history` (never generates one: the saved row is text only), clamped to 6 lines |

Every card heading carries a Tabler icon. The morning briefing page keeps only the AI summary; weather, holidays, birthdays, priority tasks, events and pending shopping live on the dashboard.

## Settings page

`/settings` edits every runtime setting (`core.settings`), a card per namespace. It is rendered from `GET /core/settings/catalog` (labels, controls, limits, defaults; see [configuration.md](configuration.md#the-settings-catalog)) plus each namespace's own GET, fetched in parallel so one failing namespace leaves only its rows out. Page logic is in `web/app/shared/settings_page.py` (pure, tested in `web/tests/test_settings.py`), the controls are macros in `_settings_widgets.html` (one per `widget`), and `static/js/settings-page.js` does the rest in the browser:

- **Search** filters the rows by label, key and description, hides empty sections, updates the counts in the section nav and keeps `?q=`.
- **Saving**: an edited row is marked; the bar at the bottom counts the changes; *Review and save* lists `key: old → new` per section (with a field's `confirm_note`), and *Save* posts only the changed fields to `POST /settings/save`. That route forwards one PUT per namespace (one per profile or relationship for the notification cascades, from the JSON editor) and answers per namespace, so a failing section keeps its rows marked and shows the backend's message while the others stay saved. It is not atomic across sections. Read-only rows and `planning.travel_times` are never sent.
- A "modified" badge shows when a value differs from the catalog default (the tooltip shows the default, so a tuning value can be set back by hand; there is no reset button).
- **Show tuning** (page head, remembered in `localStorage`): fields marked `advanced` in the catalog (chat, CS coach and metrics sections, statement import matching) are hidden until it is on; a search that matches one shows it anyway. Their fieldsets carry a *tuning* badge and come last in their card.
- **Pre-trip checklist** (Travel card, widget `checklist`): the template items grouped by anchor with an offset input each, a remove button and an add row (a typed name becomes its slug: lowercase, spaces as `-`). The whole list is one value, saved with one `PUT /travel/checklist-template`.
- **Persona additions** (Assistant card, widget `markdown`): an *Edit* button opens a dialog with the markdown next to the read-only base persona (the field's `reference`). The row shows only the length; the review lists the length change, never the text.
- Keys no field covers (`travel.checklist_seeded`, `core.paused_at`) are internal state and are not shown.

Feature pages keep a one-line summary and a link to `/settings#<namespace>`: `/plan`, `/tasks/insights` (Overload), `/travel`; `/finance/settings` redirects there.

## Pages

dashboard, tasks (+ `/tasks/insights`), notes, contacts, calendar (+ `/calendar/day/{date}`), shopping (+ `/shopping/insights`), finance, insights, briefing, chat, auth, language, cs, study, metrics (`/metrics`, `/metrics/{name}`), travel (`/travel`, `/travel/{id}`), plan (`/plan`), routines, activities, places (`/places`, `/places/{id}`, `/places/cities`, `/places/countries` and their pages, `/places/map`), settings (`/settings`). Feature-specific portal behaviour is documented in the module docs.
