from typing import Any, Dict, List
from app.assistant.commands.schemas import CommandMetadata

# --- Shared Flag Constants ---
FLAG_TAGS = {"-t": "tags", "--tags": "tags"}
FLAG_NOTES = {"-n": "additional_notes", "--notes": "additional_notes"}
FLAG_RECURRENCE = {"-r": "recurrence", "--repeat": "recurrence", "--recurrence": "recurrence"}
FLAG_STATUS = {"-s": "status", "--status": "status"}
FLAG_PRIORITY = {"-p": "priority", "--priority": "priority"}
FLAG_DUE = {"-d": "deadline", "--due": "deadline"}
FLAG_TITLE = {"-t": "title", "--title": "title"}
FLAG_LIMIT = {"--limit": "limit"}
FLAG_LINKS = {"-l": "links", "--links": "links"}
FLAG_START = {"-s": "start", "--start": "start"}
FLAG_END = {"-e": "end", "--end": "end"}
FLAG_DURATION = {"-d": "duration", "--duration": "duration"}

# --- Action-Specific Flag Compositions ---
TASK_ADD_FLAGS = {**FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_RECURRENCE}
TASK_LIST_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_LIMIT}
TASK_UPDATE_FLAGS = {**FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TITLE}

NOTE_ADD_FLAGS = {**FLAG_TAGS, **FLAG_LINKS}

EVENT_ADD_FLAGS = {**FLAG_START, **FLAG_END, **FLAG_DURATION, **FLAG_RECURRENCE, **FLAG_NOTES}

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
            "aliases": ["taskupdate", "/tu", "/taskupd"],
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
            "aliases": ["noteupdate", "/nu", "/noteupd"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
        },
        "delete": {
            "aliases": ["/notedelete", "/nd", "ndel", "/nrm", "/noterm"],
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
            "aliases": ["eventupdate", "/eu", "/eventupd", "/move"],
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
        "transaction_add": {
            "aliases": ["/transactionadd", "/tradd", ""],
            "flags": {},
            "requires_args": True
        }
    }
}

def _build_registry() -> Dict[str, CommandMetadata]:
    """Builds a flat O(1) lookup table: alias -> metadata."""
    registry = {}
    for cmd_type, actions in COMMAND_DEFINITIONS.items():
        for action_name, config in actions.items():
            meta = CommandMetadata(
                type=cmd_type,
                action=action_name,
                flags=config.get("flags", {}),
                requires_args=config.get("requires_args", False),
                arg_keys=config.get("arg_keys", [])
            )
            for alias in config["aliases"]:
                registry[alias.lower()] = meta
    return registry

COMMAND_REGISTRY = _build_registry()