from typing import Any, Dict, List
from app.assistant.commands.schemas import CommandMetadata

# --- Shared Flag Constants ---
FLAG_TAGS = {"-t": "tags", "--tags": "tags"}
FLAG_NOTES = {"-n": "additional_notes", "--notes": "additional_notes"}
FLAG_RECURRENCE = {"-r": "recurrence", "--repeat": "recurrence", "--recurrence": "recurrence"}
FLAG_STATUS = {"-s": "status", "--status": "status"}
FLAG_PRIORITY = {"-p": "priority", "--priority": "priority"}
FLAG_DUE = {"-d": "deadline", "--due": "deadline"}
FLAG_TITLE = {"-ti": "title", "--title": "title"}
FLAG_LIMIT = {"-lim": "limit", "--limit": "limit"}
FLAG_URGENCY = {"-u": "urgency", "--urgency": "urgency"}
FLAG_DAYS = {"-d": "days", "--days": "days"}
FLAG_LINKS = {"-l": "links", "--links": "links"}
FLAG_CONTENT = {"-c": "content", "--content": "content"}
FLAG_START = {"-s": "start", "--start": "start"}
FLAG_END = {"-e": "end", "--end": "end"}
FLAG_DURATION = {"-du": "duration", "--duration": "duration"}

# --- Finance Flag Constants ---
FLAG_AMOUNT = {"-a": "amount", "--amount": "amount"}
FLAG_CATEGORY = {"-c": "category", "--category": "category"}
FLAG_MERCHANT = {"-m": "merchant", "--merchant": "merchant"}
FLAG_TXN_TYPE = {"-tp": "type", "--type": "type"}
FLAG_DATE = {"-d": "date", "--date": "date"}
FLAG_ACCOUNT = {"-acc": "account", "--account": "account"}
FLAG_PERIOD = {"-p": "period", "--period": "period"}
FLAG_FROM_DATE = {"-f": "from_date", "--from": "from_date"}
FLAG_TO_DATE = {"--to": "to_date"}
FLAG_CURRENCY = {"-cu": "currency", "--currency": "currency"}
FLAG_TOP_N = {"-n": "top_n", "--top": "top_n"}
FLAG_RECURRENCE_RULE = {"-r": "recurrence_rule", "--recurrence": "recurrence_rule"}

# --- Action-Specific Flag Compositions ---
FLAG_OCCURRENCE_DATE = {"-d": "occurrence_date", "--date": "occurrence_date"}

TASK_ADD_FLAGS = {**FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_RECURRENCE}
TASK_LIST_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_LIMIT}
TASK_UPDATE_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TITLE, **FLAG_URGENCY}
TASK_COMPLETE_FLAGS = {**FLAG_OCCURRENCE_DATE}
TASK_SNOOZE_FLAGS = {**FLAG_DAYS}

NOTE_ADD_FLAGS = {**FLAG_TAGS, **FLAG_LINKS, **FLAG_TITLE, **FLAG_CONTENT}

EVENT_ADD_FLAGS = {**FLAG_START, **FLAG_END, **FLAG_DURATION, **FLAG_RECURRENCE, **FLAG_NOTES}

TXN_ADD_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_DATE, **FLAG_ACCOUNT, **FLAG_CURRENCY, **FLAG_NOTES}
TXN_LIST_FLAGS = {**FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_ACCOUNT, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_PERIOD, **FLAG_LIMIT}
TXN_UPDATE_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_DATE, **FLAG_ACCOUNT, **FLAG_CURRENCY, **FLAG_NOTES}

BUDGET_SET_FLAGS = {**FLAG_CATEGORY, **FLAG_AMOUNT}
BUDGET_STATUS_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD}

SPENDING_REPORT_FLAGS = {**FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_ACCOUNT, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE}
SPENDING_AVERAGE_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE}
SPENDING_TOP_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_TOP_N}
BALANCE_FORECAST_FLAGS = {**FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_ACCOUNT}

# --- Shopping Flag Constants ---
FLAG_STORE = {"-st": "store", "--store": "store"}
FLAG_QUANTITY = {"-q": "quantity", "--quantity": "quantity"}
FLAG_UNIT = {"-u": "unit", "--unit": "unit"}

SHOPPING_ADD_FLAGS = {**FLAG_CATEGORY, **FLAG_PRIORITY, **FLAG_QUANTITY, **FLAG_UNIT, **FLAG_STORE, **FLAG_NOTES}
SHOPPING_LIST_FLAGS = {**FLAG_STATUS, **FLAG_CATEGORY, **FLAG_PRIORITY, **FLAG_LIMIT}
SHOPPING_UPDATE_FLAGS = {**FLAG_TITLE, **FLAG_CATEGORY, **FLAG_PRIORITY, **FLAG_QUANTITY, **FLAG_STATUS}
WISHLIST_ADD_FLAGS = {**FLAG_CATEGORY, **FLAG_NOTES}
WISHLIST_LIST_FLAGS = {**FLAG_CATEGORY, **FLAG_LIMIT}

COMMAND_DEFINITIONS = {
    "task": {
        "add": {
            "description": "Create a new task with optional deadline, priority, tags, or recurrence",
            "aliases": ["/taskadd", "/t", "/ta", "/task"],
            "nl_triggers": [
                "add a task to", "add a task:", "create a task to", "create a task:",
                "create the task", "new task:", "task:",
            ],
            "flags": TASK_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"]
        },
        "list": {
            "description": "List tasks with optional filters by status, priority, tags, or deadline",
            "aliases": ["/tasklist", "/tl", "/list", "/tasks"],
            "nl_triggers": [
                "what are my pending tasks", "show me my to-do list", "show my to-do list",
                "what do i have to do today", "list my tasks", "show all my open tasks",
                "what's on my task list", "whats on my task list",
            ],
            "flags": TASK_LIST_FLAGS
        },
        "search": {
            "description": "Search tasks by keyword",
            "aliases": ["/tasksearch", "/ts", "/taskfind"],
            "nl_triggers": [
                "do i have any tasks about", "find tasks related to", "do i have anything to do about",
                "search my tasks for", "any tasks related to", "look up tasks about",
            ],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"]
        },
        "pending": {
            "description": "Show all overdue and today's pending tasks",
            "aliases": ["/pending", "/pd", "/overdue"],
            "nl_triggers": [
                "what's pending", "whats pending", "what am i behind on", "what's overdue",
                "whats overdue", "what do i still need to do today", "show me what's due today",
                "what tasks are past their deadline", "what haven't i done yet",
            ],
            "flags": {},
        },
        "update": {
            "description": "Update a task's title, status, priority, or deadline by ID",
            "aliases": ["/taskupdate", "/tu", "/taskupd"],
            "flags": TASK_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "complete": {
            "description": "Mark a task as done by ID",
            "aliases": ["/taskdone", "/td", "/done"],
            "flags": TASK_COMPLETE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "cancel": {
            "description": "Cancel a task by ID",
            "aliases": ["/taskcancel", "/tcancel", "/tc"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "snooze": {
            "description": "Snooze the no-deadline escalation reminder for a task by ID",
            "aliases": ["/tasksnooze", "/snooze"],
            "flags": TASK_SNOOZE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "description": "Delete a task permanently by ID",
            "aliases": ["/taskdelete", "/trm", "/taskrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "note": {
        "add": {
            "description": "Save a new note with optional title, tags, or links",
            "aliases": ["/noteadd", "/n", "/na", "/note"],
            "flags": NOTE_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["content"]
        },
        "search": {
            "description": "Search notes by keyword",
            "aliases": ["/notesearch", "/ns", "/notefind"],
            "nl_triggers": [
                "find my note about", "find note about", "search my notes for", "search for notes on",
                "do i have a note about", "find notes about", "find notes mentioning",
                "look for notes about", "look for notes mentioning",
            ],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"]
        },
        "list": {
            "description": "List all saved notes",
            "aliases": ["/notelist", "/nl", "/notes"],
            "nl_triggers": [
                "show all my notes", "show my notes", "list my notes", "list recent notes",
                "what notes do i have", "display my saved notes", "give me all my notes",
            ],
            "flags": {}
        },
        "update": {
            "description": "Update a note's content by ID",
            "aliases": ["/noteupdate", "/nu", "/noteupd"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "description": "Delete a note by ID",
            "aliases": ["/notedelete", "/nd", "/ndel", "/nrm", "/noterm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "event": {
        "add": {
            "description": "Add a calendar event with title, start, and optional end time or duration",
            "aliases": ["/eventadd", "/ea", "/event"],
            "flags": EVENT_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"]
        },
        "list": {
            "description": "List upcoming calendar events",
            "aliases": ["/eventlist", "/el", "/events"],
            "nl_triggers": [
                "what's on my calendar", "whats on my calendar", "show my schedule",
                "what events do i have", "what meetings do i have", "show my upcoming events",
                "what does my calendar look like",
            ],
            "flags": {}
        },
        "update": {
            "description": "Update a calendar event by ID",
            "aliases": ["/eventupdate", "/eu", "/eventupd", "/move"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "description": "Delete a calendar event by ID",
            "aliases": ["/eventdelete", "/ed", "/edel", "/eventrm", "/cancel"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "shopping": {
        "add": {
            "description": "Add an item to the shopping list",
            "aliases": ["/shop", "/sa", "/shopping", "/buy"],
            "flags": SHOPPING_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "list": {
            "description": "List shopping items with optional filters by status, category, or priority",
            "aliases": ["/shoplist", "/sl", "/shoppinglist"],
            "nl_triggers": ["show my shopping list", "what do i need to buy", "what's on my grocery list", "whats on my grocery list"],
            "flags": SHOPPING_LIST_FLAGS,
        },
        "complete": {
            "description": "Mark a shopping item as bought",
            "aliases": ["/bought", "/shopbought", "/sb"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "delete": {
            "description": "Remove a shopping item",
            "aliases": ["/shopdelete", "/shoprm", "/sdrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "update": {
            "description": "Update a shopping item by ID",
            "aliases": ["/shopupdate", "/su", "/shopupd"],
            "flags": SHOPPING_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "wishlist": {
        "add": {
            "description": "Add an item to your wishlist",
            "aliases": ["/wish", "/wa", "/wishadd"],
            "flags": WISHLIST_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "list": {
            "description": "List wishlist items",
            "aliases": ["/wishlist", "/wl"],
            "nl_triggers": ["show my wishlist", "what's on my wish list", "whats on my wish list", "list everything on my wishlist"],
            "flags": WISHLIST_LIST_FLAGS,
        },
        "delete": {
            "description": "Remove an item from the wishlist",
            "aliases": ["/wishrm", "/wd", "/wishdelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "promote": {
            "description": "Move a wishlist item to the shopping list",
            "aliases": ["/promote", "/wp", "/wishpromote"],
            "flags": {**FLAG_PRIORITY},
            "requires_args": True,
            "arg_keys": ["name"],
        },
    },
    "language": {
        "practice": {
            "description": "Start a shadowing/pronunciation practice session for a language "
            "(language_code defaults to English if omitted). Pass one or more comma-separated "
            "words/phrases instead of a count to force-practice those specific chunks, "
            "optionally with level:<CEFR> to steer a newly created chunk's difficulty",
            # /practice is a legacy alias for /shadow; kept for one release.
            "aliases": ["/shadow", "/practice", "/pr"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "count"],
        },
        "review": {
            "description": "Start an SRS review session for a language "
            "(language_code defaults to English if omitted). Pass one or more comma-separated "
            "words/phrases instead of a count to force-practice those specific chunks, "
            "optionally with level:<CEFR> to steer a newly created chunk's difficulty",
            "aliases": ["/review", "/rv"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "count"],
        },
        "produce": {
            "description": "Start a production practice session for a language "
            "(sentence, translate, journal, timed writing, or spoken speak/retell; "
            "language_code defaults to English if omitted; level:<CEFR> steers a generated "
            "retell passage's difficulty)",
            "aliases": ["/produce", "/prod"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "task_type", "count"],
        },
        "conversation": {
            "description": "Start a free-form spoken conversation practice session for a language "
            "(add 'roleplay <scenario>' for a scripted roleplay instead; "
            "language_code defaults to English if omitted; level:<CEFR> (e.g. level:a0 for a "
            "total-beginner register) steers the whole session's difficulty)",
            "aliases": ["/conversation", "/talk"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "rest"],
        },
        # Convenience alias: /roleplay <lang> <scenario> is equivalent to
        # /conversation <lang> roleplay <scenario>. Both resolve to action="conversation".
        "conversation_roleplay": {
            "description": "Start a roleplay conversation practice session for a language "
            "(language_code defaults to English if omitted; level:<CEFR> (e.g. level:a0 for a "
            "total-beginner register) steers the whole session's difficulty)",
            "action": "conversation",
            "aliases": ["/roleplay"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "rest"],
            "implicit_flags": {"mode": "roleplay"},
        },
        "stop": {
            "description": "Stop the active language practice, review, production, or conversation session",
            "aliases": ["/stop", "/stop-practice", "/stop-review", "/stop-conversation"],
            "flags": {},
        },
    },
    "cs": {
        "context": {
            "description": "Load your CS practice weak spots (weakest tags, streak, untried tags) "
            "into chat context for the next few hours",
            "aliases": ["/csmentor", "/cscontext", "/csstudy"],
            "flags": {},
        }
    },
    "recall": {
        "search": {
            "description": "Search your memories semantically by keyword",
            "aliases": ["/recall", "/rc", "/remember"],
            "nl_triggers": [
                "what did i say about", "do i have anything about", "do i have anything saved about",
                "what do i know about", "recall what i said about", "recall what i wrote about",
                "find anything i have about", "pull up what i know about", "what have i said about",
            ],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"],
        }
    },
    "weather": {
        "current": {
            "description": "Get current weather for a location",
            "aliases": ["/weather", "/wx"],
            "nl_triggers": ["what's the weather", "whats the weather", "how is the weather", "what's the forecast", "whats the forecast"],
            "flags": {"-d": "date", "--date": "date"},
            "arg_keys": ["location"]
        }
    },
    "assistant": {
        "focus": {
            "description": "Get a recommendation on what to focus on right now",
            "aliases": ["/focus", "/next", "/whatnow"],
            "nl_triggers": [
                "what should i work on", "what's my next focus", "whats my next focus",
                "what should i tackle next", "give me a focus suggestion",
            ],
            "flags": {},
        }
    },
    "reminder": {
        "set": {
            "description": "Set a reminder with a title and due time",
            "aliases": ["/remind", "/remindme"],
            "flags": {**FLAG_DUE},
            "requires_args": True,
            "arg_keys": ["title"]
        }
    },
    "help": {
        "help": {
            "description": "Show available commands, or details about a specific command",
            "aliases": ["/help", "/h", "/?"],
            "flags": {},
            "requires_args": False,
            "arg_keys": ["query"]
        }
    },
    "finance": {
        # --- Transactions ---
        "transaction_add": {
            "description": "Log a financial transaction with amount, category, and merchant",
            "aliases": ["/transactionadd", "/tra", "/transaction"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"]
        },
        # Convenience aliases that pre-set transaction type via implicit_flags.
        # Both resolve to action="transaction_add" at the service layer.
        "transaction_add_expense": {
            "description": "Log an expense quickly",
            "action": "transaction_add",
            "aliases": ["/expense", "/exp"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"],
            "implicit_flags": {"type": "expense"}
        },
        "transaction_add_income": {
            "description": "Log income quickly",
            "action": "transaction_add",
            "aliases": ["/income", "/inc"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"],
            "implicit_flags": {"type": "income"}
        },
        "transaction_list": {
            "description": "List transactions with optional filters by category, merchant, type, or period",
            "aliases": ["/transactionlist", "/trl", "/transactions"],
            "flags": TXN_LIST_FLAGS
        },
        "transaction_update": {
            "description": "Update a transaction by ID",
            "aliases": ["/transactionupdate", "/tru", "/transactionupd"],
            "flags": TXN_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "transaction_delete": {
            "description": "Delete a transaction by ID",
            "aliases": ["/transactiondelete", "/trd", "/transactionrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        # --- Budgets ---
        "budget_set": {
            "description": "Set or clear the monthly spending target for a category (omit amount to clear)",
            "aliases": ["/budgetset", "/bs", "/budget"],
            "flags": BUDGET_SET_FLAGS,
            "requires_args": True,
            "arg_keys": ["category", "amount"]
        },
        # --- Spending analytics ---
        # First positional arg is the period ("this month", "last week", "this year", etc.)
        # Falls back to current month at the service layer when omitted.
        "spending_report": {
            "description": "Get a spending breakdown report for a period",
            "aliases": ["/spendingreport", "/sr", "/spent", "/spending"],
            "flags": SPENDING_REPORT_FLAGS,
            "arg_keys": ["period"]
        },
        "spending_average": {
            "description": "Get average spending per period",
            "aliases": ["/spendingaverage", "/sav", "/avgspend"],
            "flags": SPENDING_AVERAGE_FLAGS,
            "arg_keys": ["period"]
        },
        "spending_top": {
            "description": "Get top spending categories for a period",
            "aliases": ["/spendingtop", "/stp", "/topspend", "/top5"],
            "flags": SPENDING_TOP_FLAGS,
            "arg_keys": ["period"]
        },
        # --- Balance ---
        "budget_status": {
            "description": "Check spending vs. target per category for a month",
            "aliases": ["/budgetstatus", "/bst", "/budgetlist", "/bl", "/budgets", "/budgetremaining", "/br", "/remaining", "/left"],
            "flags": BUDGET_STATUS_FLAGS,
            "arg_keys": ["period"]
        },
        "balance_forecast": {
            "description": "Forecast your balance for a future period",
            "aliases": ["/balanceforecast", "/bfc", "/forecast", "/predict"],
            "flags": BALANCE_FORECAST_FLAGS,
            "arg_keys": ["period"]
        }
    }
}

def _build_registry() -> Dict[str, CommandMetadata]:
    """Builds a flat O(1) lookup table: alias -> metadata."""
    registry = {}
    for cmd_type, actions in COMMAND_DEFINITIONS.items():
        for action_name, config in actions.items():
            actual_action = config.get("action", action_name)
            meta = CommandMetadata(
                type=cmd_type,
                action=actual_action,
                flags=config.get("flags", {}),
                requires_args=config.get("requires_args", False),
                arg_keys=config.get("arg_keys", []),
                implicit_flags=config.get("implicit_flags", {}),
                description=config.get("description", ""),
                nl_triggers=config.get("nl_triggers", []),
            )
            for alias in config["aliases"]:
                registry[alias.lower()] = meta
    return registry

COMMAND_REGISTRY = _build_registry()


def _build_nl_trigger_index() -> List[tuple]:
    """Flat list of (trigger_phrase, primary_alias), longest phrase first so a more
    specific trigger always wins over a shorter, more generic one that also matches."""
    index = []
    for actions in COMMAND_DEFINITIONS.values():
        for config in actions.values():
            primary_alias = config["aliases"][0]
            for trigger in config.get("nl_triggers", []):
                index.append((trigger.lower(), primary_alias))
    index.sort(key=lambda pair: len(pair[0]), reverse=True)
    return index

NL_TRIGGER_INDEX = _build_nl_trigger_index()
