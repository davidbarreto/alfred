from typing import Any, Dict, List
from app.assistant.commands.schemas import CommandMetadata
from app.features.organizer.calendar_events.constants import EVENT_AVAILABILITIES, EVENT_PRESENCES
from app.features.organizer.tasks.schemas import TASK_CONTEXTS

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
FLAG_ESTIMATE = {"-est": "estimate", "--estimate": "estimate"}
FLAG_CONTEXT = {"-cx": "context", "--context": "context"}
FLAG_AVAILABLE_FROM = {"--from": "available_from", "--not-before": "available_from"}
FLAG_AVAILABLE = {"--available": "available"}
FLAG_LOCATION = {"--location": "location"}
FLAG_EVENT_AVAILABILITY = {"--availability": "availability"}
FLAG_EVENT_PRESENCE = {"--presence": "presence"}
FLAG_TRAVEL = {"--travel": "travel_minutes"}
FLAG_ROUTINE = {"--routine": "routine_id"}

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

TASK_ADD_FLAGS = {
    **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_RECURRENCE, **FLAG_ESTIMATE, **FLAG_CONTEXT, **FLAG_AVAILABLE_FROM,
}
TASK_LIST_FLAGS = {
    **FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TAGS, **FLAG_LIMIT, **FLAG_CONTEXT, **FLAG_AVAILABLE,
}
TASK_UPDATE_FLAGS = {
    **FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TITLE, **FLAG_URGENCY,
    **FLAG_ESTIMATE, **FLAG_CONTEXT, **FLAG_AVAILABLE_FROM,
}

_EVENT_PLANNING_DETAILS = (
    f"Planning fields (series-wide, Alfred only, never sent to Google): availability = how much the event blocks, one of "
    f"{'/'.join(EVENT_AVAILABILITIES)} (unset: all-day events are free, timed ones blocked); presence = "
    f"{'/'.join(EVENT_PRESENCES)} (default in_person); travel_minutes = one-way travel in minutes, applied before and "
    "after the event (default 0); routine_id = an event-attached routine whose steps run around this event. "
    "Pass an empty availability or routine_id to clear it."
)
_TASK_CONTEXT_VALUES = "/".join(TASK_CONTEXTS)
_TASK_PLANNING_DETAILS = (
    f"Planning fields are optional and stay in Alfred only (never sent to Notion): estimate = minutes (whole number); "
    f"context = where it can be done, one of {_TASK_CONTEXT_VALUES}; available_from = not before this ISO date or "
    "datetime (a date alone means 00:00 local). Tags are plain names. When estimate or context is missing, ask "
    "the user and write the answers back with the update action. Pass an empty value to clear a field."
)
TASK_COMPLETE_FLAGS = {**FLAG_OCCURRENCE_DATE}
TASK_SNOOZE_FLAGS = {**FLAG_DAYS}

NOTE_ADD_FLAGS = {**FLAG_TAGS, **FLAG_LINKS, **FLAG_TITLE, **FLAG_CONTENT}

EVENT_LIST_FLAGS = {**FLAG_START, **FLAG_END, **FLAG_LIMIT}
EVENT_PLANNING_FLAGS = {**FLAG_EVENT_AVAILABILITY, **FLAG_EVENT_PRESENCE, **FLAG_TRAVEL, **FLAG_ROUTINE}
EVENT_ADD_FLAGS = {
    **FLAG_START, **FLAG_END, **FLAG_DURATION, **FLAG_RECURRENCE, **FLAG_NOTES, **FLAG_TAGS, **FLAG_LOCATION,
    **EVENT_PLANNING_FLAGS,
}
EVENT_UPDATE_FLAGS = {
    **FLAG_TITLE, **FLAG_START, **FLAG_END, **FLAG_RECURRENCE, **FLAG_NOTES, **FLAG_TAGS, **FLAG_LOCATION,
    **EVENT_PLANNING_FLAGS,
}

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

FLAG_ROUTINE_NAME = {"--name": "name"}
ROUTINE_FIELD_FLAGS = {
    **FLAG_ROUTINE_NAME, "--description": "description", "--active": "active",
    "--rule": "recurrence_rule", "--starts": "starts_on",
}
ROUTINE_STEP_FLAGS = {
    **FLAG_TITLE, "--duration": "duration_minutes", "--anchor": "anchor", "--offset": "offset_minutes",
    "--window-start": "window_start", "--window-end": "window_end", **FLAG_CONTEXT, "--location": "location",
    "--note": "checklist_note_id", "--position": "position",
}
_ROUTINE_KIND_RULE = (
    "A routine is either event-based (no recurrence rule; attach it to calendar events) or scheduled "
    "(recurrence_rule + starts_on); a routine cannot change kind while its steps or attached events do not fit."
)
_ROUTINE_OVERVIEW = (
    "Routines are daily-life rhythm, not tasks: no done state, never notify, never contain travel (use the event's "
    "travel_minutes). " + _ROUTINE_KIND_RULE + " recurrence_rule is an RRULE such as FREQ=DAILY or "
    "FREQ=WEEKLY;BYDAY=MO,TU (COUNT/UNTIL honoured); starts_on is its first date (YYYY-MM-DD)."
)
_ROUTINE_STEP_DETAILS = (
    "Timing is exactly one form. Event-based routines: anchor (start or end of the event) + offset_minutes "
    "(negative = before the anchor). Scheduled routines: window_start + window_end as HH:MM; the step happens "
    "inside that window and the planner places it, and a window exactly as long as duration_minutes is a fixed "
    f"time. duration_minutes is a whole number of minutes. context is one of {'/'.join(TASK_CONTEXTS)}. location is "
    "free text. note = id of a note used as the step's checklist. position defaults to the end. "
    "Empty values clear optional fields."
)

ACTIVITY_FIELD_FLAGS = {
    **FLAG_TITLE, "--min": "min_minutes", "--max": "max_minutes", **FLAG_CONTEXT, "--target": "target_per_week",
    **FLAG_TAGS,
}
_ACTIVITY_DETAILS = (
    "Activities are optional gap fillers, not tasks: no deadline, no done state, never escalated or notified. "
    f"min_minutes and max_minutes are the usual length in minutes; context is one of {'/'.join(TASK_CONTEXTS)}; "
    "target_per_week is a soft wish such as 3 for the gym that only shapes suggestions and is never enforced; "
    "categories are tags (comma-separated plain names). Use a recurring task instead when skipping it counts as a miss."
)
PLANNING_SETTINGS_FLAGS = {
    "--wake": "wake_time", "--sleep": "sleep_time", "--work-target": "work_target_minutes",
    "--work-windows": "preferred_work_windows", "--work-tag": "work_tag", "--office-tag": "office_tag",
    "--office-days": "office_days_per_week", "--office-min": "office_min_minutes",
}
_PLANNING_SETTINGS_DETAILS = (
    "wake_time and sleep_time are HH:MM; work_target_minutes is the daily work target in minutes (default 480); "
    "preferred_work_windows is a comma-separated list like 10:00-14:00,16:00-18:00; work_tag (default work) and "
    "office_tag (default office) name the event tags that count as work time and office days; office_days_per_week "
    "(1-7) turns the office section on and office_min_minutes is the minimum length of an event to count as an "
    "office day. Unset values switch the related section off."
)
_DAY_PLAN_GET_DETAILS = (
    "date is the first local day (YYYY-MM-DD, default today), days is 1-7 (default 1), work_minutes overrides the "
    "daily work target for this request (0 for a day off). Alfred only gathers facts; it never schedules or notifies, "
    "and free slots are not returned: derive gaps from the timeline. All datetimes carry their UTC offset; timezone is "
    "the display zone. With days=1 the day's fields sit at the top level, otherwise under days[]. "
    "Per day: timeline (events with availability/presence/notification_profile, routine_step entries around events, "
    "derived travel blocks, sorted; overlaps are only reported in warnings), routine_blocks (steps of scheduled "
    "routines with a duration and a window, fixed=true when the window is exactly the duration), all_day, work "
    "(target, committed by events tagged with the work tag, remaining, preferred windows). Once per request: "
    "preferences; overdue_tasks; due_tasks (deadline in the range or the next 3 days; you choose the day); "
    "recurring_tasks (with due_dates, or flexible=true when no specific day); backlog_tasks (undated open tasks, "
    "the pool for placing work without a date); study (open items of active plans plus language quota progress); "
    "shopping (omitted when nothing to buy); office (only when configured: goal, planned_this_week, days_left_in_week "
    "counted from the first date through Sunday); warnings. Tasks not yet available (available_from after the range) "
    "are left out. light/aware events are droppable, important/cant_miss are not. Missing estimates and contexts are "
    "assumed (30 min, anywhere) and listed in warnings: ask the user and write answers back with the task update action."
)

_DAY_PLAN_SAVE_DETAILS = (
    "days is a JSON string: a list of {\"date\": \"YYYY-MM-DD\", \"items\": [...], \"notes\": \"why / intent for that day only\"}. "
    "Each item is {\"start\": ISO datetime WITH UTC offset, \"end\": ISO datetime with offset, \"kind\": one of "
    "event/task/study_item/activity/routine_step/routine_block/break/other, \"ref_id\": id of the row it refers to (or null), "
    "\"title\": text, \"note\": optional text}. ref_id kinds: event=calendar event id, task=task id, study_item=study plan "
    "item id, routine_step and routine_block=routine step id, activity=activity id; break and other take no ref_id. "
    "Every block must start on its date (local). Only the dates in the call get a new version; other dates are untouched. "
    "Typical flow: day_plan get for the week, propose, create office events once accepted, save with per-day notes; later "
    "get_saved for the range, modify and save the changed days again."
)

COMMAND_DEFINITIONS = {
    "task": {
        "add": {
            "description": "Create a new task with optional deadline, priority, tags, or recurrence",
            "details": _TASK_PLANNING_DETAILS,
            "aliases": ["/taskadd", "/t", "/ta", "/task"],
            "nl_triggers": [
                "add a task to", "add a task:", "create a task to", "create a task:",
                "create a task.", "create the task", "new task:", "task:",
            ],
            "flags": TASK_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"]
        },
        "list": {
            "description": "List tasks with optional filters by status, priority, tags, or deadline",
            "details": (
                f"Extra filters: context ({_TASK_CONTEXT_VALUES}); available=true keeps only tasks whose "
                "available_from is unset or already past. Each task shows its estimate_minutes, context and "
                "available_from when set."
            ),
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
            "details": _TASK_PLANNING_DETAILS,
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
        "get": {
            "description": "Get a single note by ID",
            "aliases": ["/noteget", "/ng"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"]
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
            "details": _EVENT_PLANNING_DETAILS,
            "aliases": ["/eventadd", "/ea", "/event"],
            "flags": EVENT_ADD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"]
        },
        "list": {
            "description": "List calendar events in a date range (default: the next 14 days)",
            "details": (
                "start and end are ISO datetimes (an offset such as +01:00 is allowed; a date-only end means the end of "
                "that day). Recurring events are expanded into one entry per occurrence. Datetimes in the result carry "
                "their UTC offset and the result states the display `timezone`. Each event includes its tags and "
                "notification_profile: light/aware events are droppable, important/cant_miss are not."
            ),
            "aliases": ["/eventlist", "/el", "/events"],
            "nl_triggers": [
                "what's on my calendar", "whats on my calendar", "show my schedule",
                "what events do i have", "what meetings do i have", "show my upcoming events",
                "what does my calendar look like",
            ],
            "flags": EVENT_LIST_FLAGS
        },
        "update": {
            "description": "Update a calendar event by ID",
            "details": _EVENT_PLANNING_DETAILS + " Updates apply to the whole recurring series; the per-event timezone is not editable here.",
            "aliases": ["/eventupdate", "/eu", "/eventupd", "/move"],
            "flags": EVENT_UPDATE_FLAGS,
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
            "description": "Start a shadowing/pronunciation session "
            "(language_code defaults to English). Pass comma-separated words/phrases instead "
            "of a count to force-practice those chunks; optionally add level:<CEFR> to steer "
            "a newly created chunk's difficulty",
            # /practice is a legacy alias for /shadow; kept for one release.
            "aliases": ["/shadow", "/practice", "/pr"],
            "flags": {"--level": "level", "-l": "level"},
            "arg_keys": ["language_code", "count"],
        },
        "review": {
            "description": "Start an SRS review session "
            "(language_code defaults to English). Pass comma-separated words/phrases instead "
            "of a count to force-practice those chunks; optionally add level:<CEFR> to steer "
            "a newly created chunk's difficulty",
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
            "description": "Start a free-form spoken conversation session "
            "(language_code defaults to English). Add 'roleplay <scenario>' for a scripted "
            "roleplay instead. level:<CEFR> (e.g. level:a0 for total beginner) sets the "
            "session's difficulty",
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
    "study": {
        "plans": {
            "description": "List your active and backlog study plans with their open items",
            "aliases": ["/studyplans", "/study"],
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
    "pause": {
        "start": {
            "description": "Pause all reminders and briefings, and stop task urgency from escalating",
            "aliases": ["/pause", "/breath"],
            "flags": {},
            "requires_args": False,
            "arg_keys": []
        },
        "stop": {
            "description": "Resume reminders; restores escalated task urgency and shifts overdue deadlines forward",
            "aliases": ["/resume", "/unpause"],
            "flags": {},
            "requires_args": False,
            "arg_keys": []
        }
    },
    "catchup": {
        "show": {
            "description": "Suggest how to dig out of an overdue backlog: today's top tasks, spreading, dropping stale tasks",
            "aliases": ["/catchup"],
            "flags": {},
            "requires_args": False,
            "arg_keys": []
        },
        "apply": {
            "description": "Apply a catch-up suggestion: spread (re-date overdue tasks) or drop <ids> (cancel stale tasks)",
            "aliases": ["/catchupapply"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["kind", "ids"]
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
    },
    "account": {
        "list": {
            "description": "List finance accounts, optionally filtered by type, currency, or active status",
            "aliases": ["/accountlist", "/accounts"],
            "flags": {"--type": "type", "--currency": "currency", "--active": "is_active"},
        },
        "get": {
            "description": "Get a single finance account by ID",
            "aliases": ["/accountget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "category": {
        "list": {
            "description": "List all finance categories",
            "aliases": ["/categorylist", "/categories"],
            "flags": {},
        },
    },
    "recurring": {
        "list": {
            "description": "List recurring transaction rules, optionally filtered by account, type, or active status",
            "aliases": ["/recurringlist", "/recurring"],
            "flags": {"--active": "active", "--type": "type", "--account_id": "account_id"},
        },
        "get": {
            "description": "Get a single recurring transaction rule by ID",
            "aliases": ["/recurringget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "contact": {
        "list": {
            "description": "List contacts, optionally filtered by relationship (family, relative, friend, other)",
            "aliases": ["/contactlist", "/contacts"],
            "flags": {"--relationship": "relationship"},
        },
        "search": {
            "description": "Search contacts by name",
            "aliases": ["/contactsearch"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"],
        },
        "get": {
            "description": "Get a single contact by ID",
            "aliases": ["/contactget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "watcher": {
        "list": {
            "description": "List configured monitoring watchers",
            "aliases": ["/watcherlist", "/watchers"],
            "flags": {},
        },
        "get": {
            "description": "Get a single monitoring watcher by ID",
            "aliases": ["/watcherget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "alert": {
        "list": {
            "description": "List monitoring alerts, optionally filtered by status (pending, done) or watcher ID",
            "aliases": ["/alertlist", "/alerts"],
            "flags": {"--status": "status", "--config_id": "config_id"},
        },
    },
    "interview": {
        "list": {
            "description": "List interview processes, optionally filtered by company or status",
            "aliases": ["/interviewlist", "/interviews"],
            "flags": {"--company_id": "company_id", "--status": "status"},
        },
        "get": {
            "description": "Get a single interview process by ID",
            "aliases": ["/interviewget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "memory": {
        "list": {
            "description": "List stored memories, optionally filtered by category (fact, preference, relationship, skill, episodic, goal)",
            "aliases": ["/memorylist", "/memories"],
            "flags": {"--category": "category", "--active": "active"},
        },
        "search": {
            "description": "Search stored memories by keyword",
            "aliases": ["/memorysearch"],
            "flags": {"--category": "category"},
            "requires_args": True,
            "arg_keys": ["query"],
        },
    },
    "working_memory": {
        "list": {
            "description": "List active working-memory context items, optionally filtered by key substring",
            "aliases": ["/workingmemorylist", "/wmlist"],
            "flags": {"--query": "query", "--expired": "expired"},
        },
    },
    "track": {
        "list": {
            "description": "List language tracks",
            "aliases": ["/tracklist", "/tracks"],
            "flags": {"--active_only": "active_only", "--exclude_paused": "exclude_paused"},
        },
    },
    "grammar_scope": {
        "list": {
            "description": "List a language track's grammar curriculum scope, optionally filtered by status",
            "aliases": ["/grammarscope", "/grammarscopelist"],
            "flags": {"--status": "status"},
            "requires_args": True,
            "arg_keys": ["track_id"],
        },
    },
    "briefing": {
        "history": {
            "description": "List past morning/evening briefings, optionally filtered by type",
            "aliases": ["/briefinghistory"],
            "flags": {"--type": "type", "--limit": "limit"},
        },
    },
    "interview_story": {
        "add": {
            "description": "Add a STAR interview story as 'situation | task | action | result', with optional strength (1-5) and comma-separated tags",
            "aliases": ["/storyadd", "/story"],
            "nl_triggers": [
                "add a story", "save a story", "new story:", "story:",
            ],
            "flags": {"--strength": "strength", **FLAG_TAGS},
            "requires_args": True,
            "arg_keys": ["text"],
        },
        "list": {
            "description": "List interview stories, optionally filtered by tag",
            "aliases": ["/storylist", "/stories"],
            "nl_triggers": ["list my stories", "show my stories", "show all my interview stories"],
            "flags": {"--tag": "tag", **FLAG_LIMIT, "--offset": "offset"},
        },
        "search": {
            "description": "Search interview stories by keyword",
            "aliases": ["/storysearch"],
            "nl_triggers": ["find stories about", "find my stories about"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["query"],
        },
        "tag": {
            "description": "Add a tag to a story",
            "aliases": ["/storytag"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "tag"],
        },
        "assess": {
            "description": "Get AI-suggested strength assessment for a story",
            "aliases": ["/storyassess", "/assessstory"],
            "nl_triggers": ["rate story", "how strong is story", "assess story"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "interview_prep": {
        "add": {
            "description": "Add a behavioral prep question, with optional comma-separated tags",
            "aliases": ["/prepadd", "/prepquestion", "/prep"],
            "nl_triggers": ["add a prep question", "create a prep question", "prep question:"],
            "flags": {**FLAG_TAGS},
            "requires_args": True,
            "arg_keys": ["text"],
        },
        "list": {
            "description": "List prep questions, optionally filtered by tag",
            "aliases": ["/preplist", "/prepquestions"],
            "nl_triggers": ["list my prep questions", "show my prep questions"],
            "flags": {"--tag": "tag", "--limit": "limit", "--offset": "offset"},
        },
        "tag": {
            "description": "Add a tag to a prep question",
            "aliases": ["/preptag"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "tag"],
        },
        "get": {
            "description": "Get a prep question with linked stories",
            "aliases": ["/prepget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "link": {
            "description": "Link a story to a prep question with fit score (1-5)",
            "aliases": ["/preplink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["question_id", "story_id", "fit_score"],
        },
        "unlink": {
            "description": "Unlink a story from a prep question",
            "aliases": ["/prepunlink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["question_id", "story_id"],
        },
    },
    "interview_candidate": {
        "add": {
            "description": "Add a question to ask the interviewer; --category is required (e.g. Onboarding, Tech, Culture, Benefits, Logistics, Growth, Work-life)",
            "aliases": ["/candidateadd", "/candidatequestion"],
            "nl_triggers": ["add a candidate question", "add a question to ask", "question for interviewer:"],
            "flags": {**FLAG_CATEGORY},
            "requires_args": True,
            "arg_keys": ["text"],
        },
        "list": {
            "description": "List questions to ask interviewers, optionally filtered by category",
            "aliases": ["/candidatelist", "/candidatequestions"],
            "nl_triggers": ["list my candidate questions", "show questions to ask"],
            "flags": {**FLAG_CATEGORY, "--limit": "limit", "--offset": "offset"},
        },
        "categories": {
            "description": "List available question categories",
            "aliases": ["/candidatecategories"],
            "flags": {},
        },
        "get": {
            "description": "Get a candidate question by ID",
            "aliases": ["/candidateget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "metric": {
        "start": {
            "description": "Start timing a measurement, e.g. /mstart commute-work bus (series, then optional tags). Creates the series on first use",
            "aliases": ["/mstart", "/metricstart"],
            "flags": {**FLAG_TAGS, "--note": "note"},
            "requires_args": True,
            "arg_keys": ["series", "rest"],
        },
        "stop": {
            "description": "Stop the running timer (optionally name the series); --ago 5m backdates the stop",
            "aliases": ["/mstop", "/metricstop"],
            "flags": {"--ago": "ago"},
            "arg_keys": ["series"],
        },
        "log": {
            "description": "Log a value or count, e.g. /mlog weight 80 --unit kg or /mlog coffee (no value counts one event)",
            "aliases": ["/mlog", "/metriclog"],
            "flags": {**FLAG_TAGS, "--note": "note", "--unit": "unit"},
            "requires_args": True,
            "arg_keys": ["series", "value"],
        },
        "open": {
            "description": "List running timers (unfinished starts); stale ones are flagged",
            "aliases": ["/mopen", "/metricopen"],
            "flags": {},
        },
        "history": {
            "description": "Recent metric entries, optionally for one series or tag",
            "aliases": ["/mhistory", "/metrichistory"],
            "flags": {"--tag": "tag", **FLAG_LIMIT, "--offset": "offset"},
            "arg_keys": ["series"],
        },
        "discard": {
            "description": "Discard a metric entry by ID (kept in the database, excluded from stats)",
            "aliases": ["/mdiscard", "/metricdiscard"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "routine": {
        "add": {
            "description": "Create a daily-life routine (a named list of timed steps); give a recurrence rule for a scheduled one",
            "details": _ROUTINE_OVERVIEW,
            "aliases": ["/routineadd"],
            "flags": ROUTINE_FIELD_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "list": {
            "description": "List routines with their steps and attached event ids",
            "aliases": ["/routinelist", "/routines"],
            "flags": {"--active": "active"},
        },
        "get": {
            "description": "Get one routine with its steps and each step's checklist note (id, title, content)",
            "aliases": ["/routineget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "update": {
            "description": "Update a routine's name, description, active flag or recurrence rule by ID",
            "details": "recurrence_rule and starts_on are set or cleared together (empty value clears). " + _ROUTINE_KIND_RULE,
            "aliases": ["/routineupdate"],
            "flags": ROUTINE_FIELD_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a routine and its steps; events attached to it are kept and detached",
            "aliases": ["/routinedelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "add_step": {
            "description": "Add a step to a routine: routine_id, then the title; timing via anchor+offset or a window",
            "details": _ROUTINE_STEP_DETAILS,
            "aliases": ["/routinestepadd"],
            "flags": ROUTINE_STEP_FLAGS,
            "requires_args": True,
            "arg_keys": ["routine_id", "title"],
        },
        "update_step": {
            "description": "Update a routine step by step ID; setting one timing form clears the other",
            "details": _ROUTINE_STEP_DETAILS,
            "aliases": ["/routinestepupdate"],
            "flags": ROUTINE_STEP_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete_step": {
            "description": "Delete a routine step by step ID",
            "aliases": ["/routinestepdelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "attach": {
            "description": "Attach an event-based routine to a calendar event series (all occurrences get its steps)",
            "details": "id is the routine id, event_id the calendar event. Scheduled routines (with a recurrence rule) cannot be attached.",
            "aliases": ["/routineattach"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "event_id"],
        },
        "detach": {
            "description": "Detach whatever routine is attached to a calendar event",
            "aliases": ["/routinedetach"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["event_id"],
        },
    },
    "activity": {
        "add": {
            "description": "Add an optional activity for spare time (read a book, gym, draw); not a task",
            "details": _ACTIVITY_DETAILS,
            "aliases": ["/activityadd"],
            "flags": ACTIVITY_FIELD_FLAGS,
            "requires_args": True,
            "arg_keys": ["title"],
        },
        "list": {
            "description": "List active activities, optionally by tag, search text or including archived ones",
            "aliases": ["/activitylist", "/activities"],
            "flags": {"--tag": "tag", "--search": "search", "--archived": "archived", **FLAG_LIMIT},
        },
        "update": {
            "description": "Update an activity by ID; an empty value clears an optional field",
            "details": _ACTIVITY_DETAILS,
            "aliases": ["/activityupdate"],
            "flags": ACTIVITY_FIELD_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "log": {
            "description": "Log that an activity was done now (or at done_at), optionally with the minutes spent",
            "details": (
                "Logging is what counts as done. minutes is a whole number of minutes entered by hand (never timed); "
                "done_at is an ISO datetime to catch up on something done earlier (not in the future); note is free text."
            ),
            "aliases": ["/activitylog"],
            "flags": {"--minutes": "minutes", "--note": "note", "--at": "done_at"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "history": {
            "description": "Show the logged times of an activity, newest first",
            "aliases": ["/activityhistory"],
            "flags": {**FLAG_LIMIT, "--offset": "offset"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "archive": {
            "description": "Archive an activity: hidden from suggestions, logs are kept",
            "aliases": ["/activityarchive"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "unarchive": {
            "description": "Bring an archived activity back",
            "aliases": ["/activityunarchive"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "day_plan": {
        "get": {
            "description": "Everything needed to plan a day or a week: timeline, routines, tasks, study, shopping, work and office",
            "details": _DAY_PLAN_GET_DETAILS,
            "aliases": ["/dayplan"],
            "flags": {"--date": "date", "--days": "days", "--work": "work_minutes"},
            "arg_keys": ["date"],
        },
        "save": {
            "description": "Save the agreed plan for one or more dates; a date saved again keeps the old version in history",
            "details": _DAY_PLAN_SAVE_DETAILS,
            "aliases": ["/dayplansave"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["days"],
        },
        "get_saved": {
            "description": "Load the saved plan of every date in a range (a whole week in one call)",
            "details": "from and to are YYYY-MM-DD (to defaults to from; at most 62 days). version loads that version instead of the active one.",
            "aliases": ["/dayplansaved"],
            "flags": {"--to": "to", "--version": "version"},
            "requires_args": True,
            "arg_keys": ["from"],
        },
        "history": {
            "description": "List every saved version of one date's plan, newest first",
            "aliases": ["/dayplanhistory"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["date"],
        },
        "settings": {
            "description": "Show the planning preferences (wake/sleep time, work target, office goal)",
            "aliases": ["/planningsettings"],
            "flags": {},
        },
        "set_settings": {
            "description": "Change planning preferences; an empty value resets one to its default (unset)",
            "details": _PLANNING_SETTINGS_DETAILS,
            "aliases": ["/planningset"],
            "flags": PLANNING_SETTINGS_FLAGS,
        },
    },
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
