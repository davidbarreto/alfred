# Web portal

Conventions for `web/app/`. The portal is a thin client: it fetches from the backend API and renders. Business logic stays in the backend.

## Layout

| File / path | Purpose |
|---|---|
| `web/app/routes/<page>.py` | Route handlers; thin — fetch from backend API, pass to template |
| `web/app/templates/<page>.html` | Full-page Jinja2 templates; always extend `base.html` |
| `web/app/templates/_<partial>.html` | HTMX partial templates; prefixed with `_`; never extend `base.html` |
| `web/app/client.py` | Thin async HTTP wrapper around the backend API (`api.get()`, `api.post()`, ...) |
| `web/app/shared/forward.py` | Proxies portal writes to the backend and relays its error message |
| `web/app/shared/timezone.py` | `local_today()` and friends; same helpers as the backend |

The client sends `X-Alfred-Client: web` on every backend call.

## Interaction rules

HTMX actions target the smallest possible DOM element. Full-page navigation uses standard `<a href>`. Form submissions use `fetch()` + manual DOM update (not `hx-post`) when the response replaces a larger container.

## Capped cards

Cards that list things that can grow (warnings, calendar events, unlinked charges) show the first 5 and a "See all N" link to a separate page with everything (`/travel/{id}/warnings`, `/travel/{id}/unlinked`), grouped and foldable with `<details>` when there are several groups. Never an in-place expand, even when rows carry their own controls: the full page repeats them (shared row partial and script). Never render an unbounded list on a detail page.

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

## Pages

dashboard, tasks (+ `/tasks/insights`), notes, contacts, calendar (+ `/calendar/day/{date}`), shopping (+ `/shopping/insights`), finance, insights, briefing, chat, auth, language, cs, study, metrics (`/metrics`, `/metrics/{name}`), travel (`/travel`, `/travel/{id}`), plan (`/plan`), routines, activities. Feature-specific portal behaviour is documented in the module docs.
