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
FLAG_LINKS = {"-l": "links", "--links": "links"}
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
TASK_ADD_FLAGS = {**FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_RECURRENCE}
TASK_LIST_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_LIMIT}
TASK_UPDATE_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TITLE}

NOTE_ADD_FLAGS = {**FLAG_TAGS, **FLAG_LINKS}

EVENT_ADD_FLAGS = {**FLAG_START, **FLAG_END, **FLAG_DURATION, **FLAG_RECURRENCE, **FLAG_NOTES}

TXN_ADD_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_DATE, **FLAG_ACCOUNT, **FLAG_CURRENCY, **FLAG_NOTES}
TXN_LIST_FLAGS = {**FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_ACCOUNT, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_PERIOD, **FLAG_LIMIT}
TXN_UPDATE_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_TXN_TYPE, **FLAG_DATE, **FLAG_ACCOUNT, **FLAG_CURRENCY, **FLAG_NOTES}

BUDGET_ADD_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_START, **FLAG_END, **FLAG_CURRENCY}
BUDGET_LIST_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD}
BUDGET_UPDATE_FLAGS = {**FLAG_AMOUNT, **FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_START, **FLAG_END}

SPENDING_REPORT_FLAGS = {**FLAG_CATEGORY, **FLAG_MERCHANT, **FLAG_ACCOUNT, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE}
SPENDING_AVERAGE_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE}
SPENDING_TOP_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_TOP_N}
BUDGET_REMAINING_FLAGS = {**FLAG_CATEGORY, **FLAG_PERIOD}
BALANCE_FORECAST_FLAGS = {**FLAG_PERIOD, **FLAG_FROM_DATE, **FLAG_TO_DATE, **FLAG_ACCOUNT}

COMMAND_DEFINITIONS = {
    "task": {
        "add": {
            "aliases": ["/taskadd", "/t", "/ta", "/task"],
            "flags": TASK_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["task"]
        },
        "list": {
            "aliases": ["/tasklist", "/tl", "/list", "/tasks"],
            "flags": TASK_LIST_FLAGS
        },
        "update": {
            "aliases": ["/taskupdate", "/tu", "/taskupd"],
            "flags": TASK_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "complete": {
            "aliases": ["/taskdone", "/td", "/done"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "aliases": ["/taskdelete", "/trm", "/taskrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "note": {
        "add": {
            "aliases": ["/noteadd", "/n", "/na", "/note"],
            "flags": NOTE_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["content"]
        },
        "search": {
            "aliases": ["/notesearch", "/ns", "/notefind"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"]
        },
        "list": {
            "aliases": ["/notelist", "/nl", "/notes"],
            "flags": {}
        },
        "update": {
            "aliases": ["/noteupdate", "/nu", "/noteupd"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "aliases": ["/notedelete", "/nd", "/ndel", "/nrm", "/noterm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "event": {
        "add": {
            "aliases": ["/eventadd", "/ea", "/event"],
            "flags": EVENT_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"]
        },
        "list": {
            "aliases": ["/eventlist", "/el", "/events"],
            "flags": {}
        },
        "update": {
            "aliases": ["/eventupdate", "/eu", "/eventupd", "/move"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "aliases": ["/eventdelete", "/ed", "/edel", "/eventrm", "/cancel"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        }
    },
    "help": {
        "help": {
            "aliases": ["/help", "/h", "/?"],
            "flags": {},
            "requires_args": True
        }
    },
    "finance": {
        # --- Transactions ---
        "transaction_add": {
            "aliases": ["/transactionadd", "/tra", "/transaction"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"]
        },
        # Convenience aliases that pre-set transaction type via implicit_flags.
        # Both resolve to action="transaction_add" at the service layer.
        "transaction_add_expense": {
            "action": "transaction_add",
            "aliases": ["/expense", "/exp"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"],
            "implicit_flags": {"type": "expense"}
        },
        "transaction_add_income": {
            "action": "transaction_add",
            "aliases": ["/income", "/inc"],
            "flags": TXN_ADD_FLAGS,
            "requires_args": False,
            "arg_keys": ["description"],
            "implicit_flags": {"type": "income"}
        },
        "transaction_list": {
            "aliases": ["/transactionlist", "/trl", "/transactions"],
            "flags": TXN_LIST_FLAGS
        },
        "transaction_update": {
            "aliases": ["/transactionupdate", "/tru", "/transactionupd"],
            "flags": TXN_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "transaction_delete": {
            "aliases": ["/transactiondelete", "/trd", "/transactionrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        # --- Budgets ---
        "budget_add": {
            "aliases": ["/budgetadd", "/ba", "/budget"],
            "flags": BUDGET_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"]
        },
        "budget_list": {
            "aliases": ["/budgetlist", "/bl", "/budgets"],
            "flags": BUDGET_LIST_FLAGS
        },
        "budget_update": {
            "aliases": ["/budgetupdate", "/bu", "/budgetupd"],
            "flags": BUDGET_UPDATE_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "budget_delete": {
            "aliases": ["/budgetdelete", "/bd", "/budgetrm"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        # --- Spending analytics ---
        # First positional arg is the period ("this month", "last week", "this year", etc.)
        # Falls back to current month at the service layer when omitted.
        "spending_report": {
            "aliases": ["/spendingreport", "/sr", "/spent", "/spending"],
            "flags": SPENDING_REPORT_FLAGS,
            "arg_keys": ["period"]
        },
        "spending_average": {
            "aliases": ["/spendingaverage", "/sav", "/avgspend"],
            "flags": SPENDING_AVERAGE_FLAGS,
            "arg_keys": ["period"]
        },
        "spending_top": {
            "aliases": ["/spendingtop", "/stp", "/topspend", "/top5"],
            "flags": SPENDING_TOP_FLAGS,
            "arg_keys": ["period"]
        },
        # --- Balance ---
        "budget_remaining": {
            "aliases": ["/budgetremaining", "/br", "/remaining", "/left"],
            "flags": BUDGET_REMAINING_FLAGS,
            "arg_keys": ["period"]
        },
        "balance_forecast": {
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
                implicit_flags=config.get("implicit_flags", {})
            )
            for alias in config["aliases"]:
                registry[alias.lower()] = meta
    return registry

COMMAND_REGISTRY = _build_registry()
