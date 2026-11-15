# Code Conventions

Detailed backend, portal and test conventions. The short rules that apply to every change live in `CLAUDE.md`.

## Backend feature module layout

Every domain feature lives under `app/features/<domain>/<feature>/` and follows this file structure:

| File | Purpose |
|---|---|
| `tables.py` | SQLAlchemy ORM models (table definitions only; no business logic) |
| `schemas.py` | Pydantic models: `<Entity>Create`, `<Entity>Update`, `<Entity>Read`, `<Entity>Filters` |
| `repository.py` | A single `<Entity>Repository` class; all DB queries live here; no business logic |
| `service.py` | A single `<Entity>Service` class; orchestrates repo + provider calls; no raw DB access |
| `prompts.py` | Static strings used as LLM system prompts or prompt templates |
| `recurrence.py` | Example of a pure utility module: shared domain logic with no DB/IO dependencies |

When a feature needs multiple services (e.g. briefing), use descriptive prefixes: `summary_service.py`, `formatter_service.py`.

## Pydantic schema naming

- `<Entity>Create`: POST request body; all required fields
- `<Entity>Update`: PATCH request body; all fields `Optional`, `exclude_unset=True` in callers
- `<Entity>Read`: response model; returned by routes; `model_config = {"from_attributes": True}`; always exposes `created_at` and `updated_at` for new entities (each new table declares both columns: `Base` is a plain `declarative_base()` and does not add them). Existing tables that lack them are not retrofitted.
- `<Entity>Filters`: query-parameter class; plain `__init__` (not `BaseModel`), uses `Annotated[X, Query()]`; used via `Depends()` in routes
  - Always give the parameter a plain-value default: `offset: Annotated[int, Query(ge=0)] = 0`. Never write `offset: int = Query(0, ge=0)`: that makes the `Query(...)` sentinel object itself the default, which is fine when FastAPI resolves it via `Depends()` but crashes (e.g. `int() argument must be a ... not 'Query'` deep in a repository `.offset()`/`.limit()` call) whenever the `Filters` class is constructed directly, e.g. from a command handler in `app/assistant/commands/handlers/`. Every field a handler might not explicitly pass needs the plain-value form.
  - Caveat: `Annotated[X, Query(...)] = default` breaks FastAPI's Pydantic `TypeAdapter` (`PydanticUserError: ... is not fully defined`) in a `schemas.py` that has `from __future__ import annotations` at the top, because postponed evaluation turns the annotation into a string FastAPI can't resolve. So: new `Filters` classes should skip `from __future__ import annotations` in that file and use the safe `Annotated` form. If a file already has `from __future__ import annotations` (e.g. legacy modules), keep the bare `Query(...)` default instead, and make sure every command handler that constructs that `Filters` class passes every field explicitly (don't rely on the default at all).

## Repository conventions

- One class per file: `class <Entity>Repository`
- Constructor takes only `session: AsyncSession`
- Method names: `get_<entity>`, `get_<entities>`, `create_<entity>`, `update_<entity>`, `delete_<entity>`; domain-specific names allowed (e.g. `complete_occurrence`)
- All queries use SQLAlchemy 2.0 style: `select()`, `session.execute()`, `scalars()`

## Service conventions

- One class per file: `class <Entity>Service`
- Constructor takes `provider: StorageProvider, session: AsyncSession` (or just `session` if no external provider)
- Delegates all DB access to `self._repo`; never calls `session.execute()` directly
- Private helper functions at module level are prefixed with `_`; shared helpers go in a dedicated utility module

## API route conventions

- Thin handlers only: validate input, call service, return schema
- `router = APIRouter(prefix="/...", tags=[...], dependencies=[Depends(require_auth)])`
- All routes return typed Pydantic `response_model`; never return bare `dict`
- Place static path routes (e.g. `/history`) **before** parameterised routes (e.g. `/{id}`) to avoid routing conflicts
- All `Depends()` factories are declared in `app/dependencies.py` as `Annotated` type aliases (e.g. `TaskServiceDep`)

## Integration module layout

External provider integrations live under `app/integrations/<provider>/`:

| File | Purpose |
|---|---|
| `client.py` | Raw HTTP/SDK client; wraps the external API; no business logic |
| `storage_provider.py` | Implements the `StorageProvider` protocol for write-through cache |
| `tables.py` / `schemas.py` / `repository.py` | Only present when the integration persists its own data |

## Web portal conventions

Route handlers in `web/app/routes/` stay thin: fetch from the backend API through `web/app/client.py`, pass to a template. Full pages extend `base.html`; HTMX partials are prefixed `_` and never extend it. Paginated sections use the `limit + 1` / `_pagination()` pattern. **Cap list-like cards** (warnings, events, charges, anything that can grow long): the detail page shows only the first 5 plus a "See all N" link to a **separate page** that lists everything (grouped and foldable when there are several groups). Always a separate page, never an in-place expand, even when rows carry their own controls (the full page repeats them). Never render an unbounded list on a detail page. Full conventions: `docs/portal.md`.

## SQLAlchemy / Alembic details

- All models declare `created_at` / `updated_at` timestamps
- Foreign keys are always explicit; use `ondelete` cascade only where the child has no value without the parent. Where history matters the FK is `RESTRICT` and deletion is refused with a 409 (metrics, shopping products, activities)
- Enum value sets are defined once in Python (`TASK_CONTEXTS`, `EVENT_AVAILABILITIES`, `EVENT_PRESENCES`) and feed the Pydantic types, the CHECK constraints and the MCP descriptions
- Migrations must be reversible (`downgrade` implemented)
- A migration is edited only while it is unpushed: when several unpushed commits change the same migration file, squash them so the file is introduced (or changed) in one commit. Also squash when a later unpushed commit undoes an earlier one (add then delete, or delete then add, the same change), so the history carries only the net result. Once any commit that touches a migration has been pushed, never edit that file again; add a new migration instead
- After schema changes, verify all affected modules still align
- Tag names (any tag table) are stored trimmed and lowercase: normalize on write with `normalize_tag_name` (`app/shared/tags.py`) or the schema validators, so "Family" and "family" never coexist
- Boolean columns use plain adjective/state names (`active`, `enabled`, `all_day`, `case_sensitive`), not an `is_` prefix, and Pydantic fields mirror the column name. Some older columns still use `is_*` (`is_done`, `is_active`, `is_archived`, ...); leave them until they are standardized deliberately, but don't add new ones. State-change timestamps are `<verb>_at` (`archived_at`, `deleted_at`, `completed_at`); prefer a timestamp over a boolean when "when" matters.

## Logging

Every module that performs business logic, external I/O, or mutation must have a module-level logger:

```python
import logging
logger = logging.getLogger(__name__)
```

| Level | When to use |
|---|---|
| `ERROR` | Unrecoverable failures: LLM call failed, external API error, unexpected exception |
| `WARNING` | Unexpected conditions that are handled: auth rejection, OAuth not configured, truncated LLM response |
| `INFO` | Successful mutations (create / update / delete / complete) and high-level operation results |
| `DEBUG` | Read operations, "not found" on expected paths, item counts, internal flow details |

Always use `%s` style, never f-strings:

```python
logger.info("Task created: id=%d title=%r", task.id, task.title)
logger.info("Task updated: id=%d fields=%s", task_id, list(data.model_dump(exclude_unset=True).keys()))
logger.debug("Task update: id=%d not found", task_id)
logger.error("LLM call failed: session_id=%s error=%s", session_id, exc)
logger.warning("Auth failed: invalid token")
```

Where logs belong:
- **Service layer**: primary location; log after every mutation and on significant errors
- **Integration clients**: log external call failures and notable responses (latency, token counts)
- **Auth middleware**: log rejected requests at WARNING
- **Routes**: do NOT add request-level logging (uvicorn.access covers it); only log if a route contains logic not delegated to a service
- **Repositories**: do NOT log; log at the service layer instead

Content rules:
- Always include the entity ID and 1-2 key identifying fields (name, title, source)
- For updates, log the changed field names, not values (values may be sensitive)
- Never log passwords, tokens, raw user messages, or financial amounts at INFO or above
