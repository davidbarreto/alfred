# Assistant layer (commands, intents, MCP, Telegram menu)

Everything under `backend/app/assistant/`: a command registry shared by Telegram, the MCP server and the chat, plus natural-language intent detection. Read this before adding or changing a command.

## Commands

- Commands are declared in `COMMAND_DEFINITIONS` (`app/assistant/commands/registry.py`) and handled by per-domain handlers in `app/assistant/commands/handlers/`. A resolver parses the text and an executor runs the handler.
- Handlers build Pydantic models with `build_model()` so bad input is a 400, not a 500.
- Handlers that construct a `Filters` class directly must not rely on `Query(...)` defaults; see `CLAUDE.md` (Pydantic schema naming).
- Domain conflicts are wrapped in `HTTPException(409)` by the handler so Telegram/MCP logs a warning, not an error.

### Argument parsing

The resolver splits positional args on whitespace and gives the *last* `arg_key` the remainder, and MCP reserves the name `action`. So multi-field text cannot be positional. Examples:

- `/storyadd situation | task | action | result --strength 4 -t leadership,conflict` (single `text` arg, split on `|` in the handler)
- `/candidateadd How is on-call organised? --category Tech`

### `description` and `details`

Command definitions take an optional `details` field. It is not sent to Telegram; it is appended to the MCP tool description and is where enum values, units, formats and workflow belong. `description` stays one line; `details` only adds to it.

MCP params are strings, so structured input (for example `day_plan save`'s `days`) is a JSON string validated by the handler with a 400 message.

## Telegram command menu

Telegram's `setMyCommands` API has two limits that fail `POST /integration/telegram/set-commands` for *all* commands, not just the offending one:

- Each command `description` is capped at 256 characters (BadRequest 400 otherwise). Keep `description` at **200 characters or less** for headroom.
- The whole list is rejected with `BOT_COMMANDS_TOO_MUCH` when the combined command + description text exceeds ~5.7k characters, well before the documented 100-command cap (5679 accepted, 5825 rejected on 2026-10-23).

Only the daily-use commands listed in `_MENU_COMMANDS` (`app/api/routes/integrations/telegram.py`) are registered with Telegram. Add a command there to put it in the `/` menu; the rest still work when typed (for example `/catchup`, `/catchupapply`). `_fit_to_budget` truncates descriptions uniformly if the menu ever exceeds a 5000-character budget.

## Natural language (intents)

Typed text and Telegram voice go through intent detection (`app/assistant/intents/`):

1. A 1-NN embedding match against `intent_examples.py` picks the intent (for example `metric.start`).
2. Extraction schemas in `extraction_service.py` pull the arguments. Their field names must match the handler's argument keys.
3. The example set is re-seeded on deploy.

**Misrouted phrases are fixed by adding examples, not by changing resolver logic.** Sparse examples are the usual cause of misclassification.

## Travel links

`travel_link` (`add`, `list`, `update`, `delete`, `suggest`) takes its owner as one of `--trip`, `--place`, `--city`, `--country` (id or name; an ambiguous city name is refused with its countries). `suggest` only reports where to look and what is saved; the web search is done by the MCP client, never by the backend. It is not in the Telegram menu (`_MENU_COMMANDS`). Restart the MCP container after a deploy that adds or changes commands.

## Locations

`location` (`add`, `list`, `show`, `update`, `delete`) resolves a location by id or name, takes shopping category names in `--sells` and travel minutes from existing locations in `--from` (`home:metro=20,foot=35;office:car=10`); `show` includes the travel times. Events link to a location with `event add/update --at <id or name>` (`place_id`; `--location` is the calendar's free text). Like `travel_link suggest`, the web search for opening hours is done by the MCP client and saved only after the user confirms; Alfred never searches. Not in the Telegram menu. Details: [modules/places.md](modules/places.md).

## Recall sources

`recall search` embeds-searches the `memory`, `note`, `note_title` and `task` sources plus the travel notes sources (`trip_note`, `leg_note`, `stay_note`, `visit_note`, `place_note`). A module that wants its free text recallable embeds it under its own source type and adds that type to `_SOURCE_TYPES` in `handlers/recall.py`.

## MCP

The MCP server (`mcp/`) builds one `alfred_*` tool per command group (`alfred_task`, `alfred_metric`, `alfred_day_plan`, ...) from the backend's command catalog. The catalog is fetched once at container startup, so a backend-only deploy does not refresh the tool schema Claude sees until the MCP container restarts. Calls send `X-Alfred-Client: mcp`.
