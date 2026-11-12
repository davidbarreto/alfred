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
    **FLAG_STATUS, **FLAG_DUE, **FLAG_PRIORITY, **FLAG_TITLE, **FLAG_URGENCY, **FLAG_TAGS,
    **FLAG_ESTIMATE, **FLAG_CONTEXT, **FLAG_AVAILABLE_FROM,
}

_EVENT_PLANNING_DETAILS = (
    f"Planning fields (series-wide, Alfred only, never sent to Google): availability = how much the event blocks, one of "
    f"{'/'.join(EVENT_AVAILABILITIES)} (unset: all-day events are free, timed ones blocked); presence = "
    f"{'/'.join(EVENT_PRESENCES)} (default in_person); travel_minutes = one-way travel in minutes, applied before and "
    "after the event (default 0); routine_id = an event-attached routine whose steps run around this event. "
    "Pass an empty availability or routine_id to clear it."
)
_EVENT_SKIP_DETAILS = (
    "id is the event id and date the day of the occurrence to leave out. Alfred only: the event in Google Calendar is "
    "untouched, so use it for a meeting you will not attend; the occurrence disappears from event lists, the day plan "
    "and reminders. The date must be a real occurrence of a recurring event. Undo with unskip; the skipped dates of a "
    "series are listed in its `skips`."
)
_EVENT_RESCHEDULE_DETAILS = (
    "Moves ONE occurrence of a recurring event without touching the series: id is the event id, date the day the series has "
    "that occurrence on (YYYY-MM-DD), start the new start (HH:MM on that day, or an ISO datetime to move it to another day) and "
    "end the new end (optional: the occurrence keeps its length). It is written through to Google Calendar as an exception of "
    "that instance, so attendees' calendars show it too; all-day occurrences cannot be moved. Use skip instead for a meeting "
    "you will not attend, update to change the whole series. A moved occurrence appears at its new time in lists, the day "
    "plan and reminders, and is listed in the series' `overrides`. Undo with unreschedule."
)
_EVENT_END_SERIES_DETAILS = (
    "id is the event id and date the first day the series no longer happens, so the last occurrence is the one before "
    "it. Past occurrences are kept. Replaces any UNTIL/COUNT of the rule and is written through to Google Calendar. "
    "Use delete instead to remove the whole series."
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
SHOPPING_UPDATE_FLAGS = {**FLAG_TITLE, **FLAG_CATEGORY, **FLAG_PRIORITY, **FLAG_QUANTITY, **FLAG_UNIT, **FLAG_STATUS}
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
    "--work-windows": "preferred_work_windows", "--workdays": "workdays", "--work-tag": "work_tag", "--office-tag": "office_tag",
    "--office-days": "office_days_per_week", "--office-min": "office_min_minutes", "--conventions": "conventions",
    "--travel": "travel_times",
}
_PLANNING_SETTINGS_DETAILS = (
    "wake_time and sleep_time are HH:MM; work_target_minutes is the daily work target in minutes (default 480); "
    "preferred_work_windows is a comma-separated list like 10:00-14:00,16:00-18:00; workdays is a comma-separated "
    "list of mon,tue,wed,thu,fri,sat,sun (default mon-fri) and days outside it get a work target of 0; work_tag (default work) and "
    "office_tag (default office) name the event tags that count as work time and office days; office_days_per_week "
    "(1-7) turns the office section on and office_min_minutes is the minimum length of an event to count as an "
    "office day; conventions is free text (max 2000 characters) with the user's standing planning rules, returned in "
    "the preferences of every day plan get so each client applies them without being told again; travel_times lists door-to-door minutes between two places by each mode, written [origin>]place:mode=minutes[,mode=minutes];... "
    "where the origin defaults to home (e.g. office:metro=50,car=20;office>school:car=20,walk=10; up to 20 entries, empty resets). "
    "A trip counts both ways unless the reverse is listed too. They come back in the preferences as [{origin, place, mode, minutes}] so clients "
    "derive leave-home times and transport blocks without asking. "
    "Unset values switch the related section off."
)
_DAY_PLAN_GET_DETAILS = (
    "date is the first local day (YYYY-MM-DD, default today), days is 1-7 (default 1), work_minutes overrides the "
    "daily work target for this request (0 for a day off). Alfred only gathers facts; it never schedules or notifies, "
    "and free slots are not returned: derive gaps from the timeline. All datetimes carry their UTC offset; timezone is "
    "the display zone. With days=1 the day's fields sit at the top level, otherwise under days[]. "
    "Per day: timeline (events with availability/presence/notification_profile, routine_step entries around events, "
    "derived travel blocks, sorted; overlaps are only reported in warnings), routine_blocks (steps of scheduled "
    "routines with a duration and a window, fixed=true when the window is exactly the duration), all_day, work "
    "(target, committed by events tagged with the work tag plus the saved work blocks and saved task blocks of work-tagged tasks, missed blocks excluded, overlaps counted once, remaining, preferred windows). Once per request: "
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
    "event/task/study_item/activity/routine_step/routine_block/work/transport/meal/break/other, \"ref_id\": id of the row it refers to (or null), "
    "\"title\": text, \"note\": optional text}. ref_id kinds: event=calendar event id, task=task id, study_item=study plan "
    "item id, routine_step and routine_block=routine step id, activity=activity id. Free-form kinds take no ref_id: work (focused work "
    "that is not a specific task, counts toward the day's committed work time), transport (a commute or trip leg such as home to office or "
    "metro to school; use it for travel that is NOT already covered by an event's travel_minutes, since those legs come as derived travel "
    "blocks), meal, break and other. Choose the kind by what the block is: ANY eating block (breakfast, lunch, dinner, snack, eat, have lunch) "
    "is kind meal, never break; break is only a pause to rest with no meal in it (coffee, walk, nap, stretch); other is for what fits none of the kinds. "
    "A saved block may carry missed=true: the user marked it as not done (the task stays open, it is not done or overdue because of it). "
    "A block may instead carry done=true (the user confirmed it; marking one clears the other). Blocks with neither flag whose end has "
    "passed are unmarked: do not assume they happened. "
    "Missed blocks do not count as committed work; when you re-plan that task for another day, place it once there and do not treat the "
    "missed block as a second occurrence. "
    "Every block must start on its date (local). Only the dates in the call get a new version; other dates are untouched. "
    "Typical flow: day_plan get for the week, propose, create office events once accepted, save with per-day notes; later "
    "get_saved for the range, modify and save the changed days again (for a small change use edit instead of resending whole days). "
    "The response lists only id, plan_date, version and block count per date, not the blocks."
)

_DAY_PLAN_EDIT_DETAILS = (
    "Changes part of days that are already saved without resending them. days is a JSON string: a list of "
    "{\"date\": \"YYYY-MM-DD\", \"replace_from\": \"HH:MM\", \"replace_to\": \"HH:MM\", \"items\": [...], \"notes\": optional}. "
    "Every block of that date whose start is in [replace_from, replace_to) (local time) is removed and replaced by items (same shape as in "
    "save; an empty list just removes them). All other blocks, including their done/missed flags, are kept. notes replaces the day's notes "
    "when given. Each edited date gets a new version, like save, and must already have an active saved plan. Several dates can "
    "be edited in one call (e.g. the same slice on Mon-Thu, with items per date). Returns id, plan_date, version and block count per date."
)

_DAY_PLAN_REVIEW_DETAILS = (
    "from is YYYY-MM-DD and to defaults to from + 6 days (a week). Counts, per planned thing in the active saved plans of the range "
    "(calendar events are left out), how often it was planned, done, missed, unmarked (ended without any mark: not known to have "
    "happened) or upcoming, plus the dates it was missed. Worst first. Use it to plan the next week instead of loading every saved day."
)

_DAY_PLAN_MISS_DETAILS = (
    "Use this when the user says they did not do something that was planned (\"I skipped training today\"), instead of "
    "saving the day again: it only flags the block (missed=true) in the day's active saved plan and creates no new version. "
    "date is the plan's day (YYYY-MM-DD). Identify the block with ref_id (kind defaults to task; use the same kind as in the "
    "saved plan) or with part of its title for free-form blocks; start (HH:MM, local) picks one when the same thing is planned "
    "twice that day. The task itself is not touched: it stays open and can be placed on another day. unmiss undoes it. "
    "done flags a block as done in the same way (and clears a missed mark); undone removes the done flag."
)

# --- Travel ---
_TRAVEL_FORMATS = (
    "Dates are YYYY-MM-DD; date-times are ISO local wall time (2026-12-17T06:30) read in the matching IANA zone "
    "(Europe/Lisbon). Ids come from the list/get actions. An empty value clears an optional field."
)
_TRIP_OVERVIEW = (
    "A trip is a journey with dates, legs (flights, trains, ...), stays (hotels) and visits (museums, dinners). "
    "tags describe the trip (Family, Work); finance_tags is a comma-separated list of finance tags stamped on expenses "
    "dated within the trip. " + _TRAVEL_FORMATS
)
_LEG_OVERVIEW = (
    "A leg is one flight, train, bus, ferry or car ride of a trip. mode is one of flight/train/bus/ferry/car/other. "
    "departs and arrives are the local wall times at origin and destination with their own zones (departs_tz, "
    "arrives_tz), so both zones are required. from_code/to_code are IATA airport codes; ref is the booking code (PNR), "
    "url the booking link. " + _TRAVEL_FORMATS
)
_STAY_OVERVIEW = (
    "A stay is a lodging period. Give place (id of an existing place) or hotel (a name, with optional city/country/"
    "maps_url, reused if a hotel with that name and city exists). check_in/check_out are local wall times at the hotel "
    "in its zone (tz); grade is 1-5 after the stay. trip is optional (a weekend away needs no trip). " + _TRAVEL_FORMATS
)
_PLACE_OVERVIEW = (
    "A place is a hotel, restaurant, cafe, activity, museum, attraction, shop or other, independent of any trip. "
    "kind is one of hotel/restaurant/cafe/activity/museum/attraction/shop/other. maps_url is the user's own link; lat/lng "
    "are optional and user-supplied. notes holds lasting facts (\"book the terrace\"). A place's grade is the average of "
    "its graded visits and stays. " + _TRAVEL_FORMATS
)
_VISIT_OVERVIEW = (
    "A visit is one occurrence of going to a place: status planned/visited/missed, optional trip, date and time "
    "(HH:MM, real for a reservation or approximate to order the day). A planned visit with no trip is the wishlist. "
    "place is an id or a name: a name reuses an existing place (same name, and city if given) or creates one of the given "
    "kind (default other). grade 1-5 only for a visited visit. " + _TRAVEL_FORMATS
)
_TRAVEL_LINK_DETAILS = (
    "Links a finance transaction (by id) to this item as what paid for it; one transaction can be linked to several items "
    "and counts once in the trip total. Transfers can't be linked. Costs are derived from the linked transactions."
)

TRIP_FLAGS = {
    "--start": "start", "--end": "end", "--travelers": "travelers", "--preferences": "preferences",
    "--notes": "notes", "--finance-tags": "finance_tags", **FLAG_TAGS, "--checklist-note": "checklist_note",
}
LEG_FLAGS = {
    "--from": "origin", "--to": "destination", "--from-code": "origin_code", "--to-code": "destination_code",
    "--departs": "departs", "--arrives": "arrives", "--departs-tz": "departs_tz", "--arrives-tz": "arrives_tz",
    "--carrier": "carrier", "--number": "number", "--ref": "booking_ref", "--url": "booking_url", "--seat": "seat",
    "--notes": "notes",
}
STAY_FLAGS = {
    "--place": "place", "--hotel": "hotel", "--city": "city", "--country": "country", "--maps-url": "maps_url",
    "--check-in": "check_in", "--check-out": "check_out", "--tz": "tz", "--ref": "booking_ref", "--url": "booking_url",
    "--notes": "notes", "--grade": "grade", "--trip": "trip",
}
PLACE_FLAGS = {
    "--kind": "kind", "--city": "city", "--country": "country", "--maps-url": "maps_url", "--lat": "lat", "--lng": "lng",
    "--address": "address", "--notes": "notes", **FLAG_TAGS,
}
PLACE_LIST_FLAGS = {
    "--kind": "kind", "--city": "city", "--country": "country", "--tag": "tag", "--min-grade": "min_grade",
    "--ungraded": "ungraded", "--status": "status", "--no-trip": "no_trip", **FLAG_LIMIT, "--offset": "offset",
}
VISIT_FLAGS = {
    "--trip": "trip", "--date": "date", "--time": "time", "--status": "status", "--grade": "grade", "--notes": "notes",
    "--kind": "kind", "--city": "city", "--country": "country", "--place": "place",
}
VISIT_LIST_FLAGS = {
    "--trip": "trip", "--place": "place", "--status": "status", "--no-trip": "no_trip", "--from": "date_from",
    "--to": "date_to", **FLAG_LIMIT, "--offset": "offset",
}

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
        "skip": {
            "description": "Skip one occurrence of a recurring event (a date, YYYY-MM-DD)",
            "details": _EVENT_SKIP_DETAILS,
            "aliases": ["/eventskip", "/skip"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "date"]
        },
        "unskip": {
            "description": "Bring back a skipped occurrence of a recurring event (a date, YYYY-MM-DD)",
            "aliases": ["/eventunskip", "/unskip"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "date"]
        },
        "reschedule": {
            "description": "Move one occurrence of a recurring event to another time (the series is untouched)",
            "details": _EVENT_RESCHEDULE_DETAILS,
            "aliases": ["/eventreschedule", "/reschedule"],
            "flags": {**FLAG_START, **FLAG_END},
            "requires_args": True,
            "arg_keys": ["id", "date"]
        },
        "unreschedule": {
            "description": "Put a moved occurrence of a recurring event back at its series time (a date, YYYY-MM-DD)",
            "aliases": ["/eventunreschedule", "/unreschedule"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "date"]
        },
        "endseries": {
            "description": "End a recurring event: its last occurrence is the one before a date (YYYY-MM-DD)",
            "details": _EVENT_END_SERIES_DETAILS,
            "aliases": ["/eventend", "/endseries"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "date"]
        },
        "delete": {
            "description": "Delete a calendar event by ID",
            "details": "Deletes the whole event; for a recurring one that removes every occurrence, past ones included. To miss a single occurrence use skip, to stop the series use endseries.",
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
            "details": (
                "Each thing you buy is one product (matched by name, ignoring case). A new name creates the product "
                "with the given category and unit as its defaults; an existing one reuses them, so unit and quantity "
                "can be omitted. Rejected with 409 when the product is already pending on the list."
            ),
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
    "travel_trip": {
        "list": {
            "description": "List trips: current (upcoming + ongoing, default), upcoming, ongoing, past or all; filter by tag or name",
            "details": _TRIP_OVERVIEW + " The first argument is the status filter.",
            "aliases": ["/trips", "/triplist"],
            "flags": {"--tag": "tag", "--q": "q", "--city": "city", "--country": "country", **FLAG_LIMIT},
            "arg_keys": ["status"],
        },
        "get": {
            "description": "Show a trip (by id or name): dates, legs, stays, itinerary, warnings, leave-home time and cost",
            "details": "The trip argument is an id or a name (the most relevant match is used). Planned and missed visits of an ended trip are hidden unless all_visits is true.",
            "aliases": ["/trip", "/tripget"],
            "flags": {"--all-visits": "all_visits"},
            "requires_args": True,
            "arg_keys": ["trip"],
        },
        "add": {
            "description": "Create a trip: name, then --start and --end dates (YYYY-MM-DD), optional travelers, tags, finance tags",
            "details": _TRIP_OVERVIEW,
            "aliases": ["/tripadd"],
            "flags": TRIP_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "update": {
            "description": "Update a trip by ID: name, dates, travelers, preferences, notes, tags, finance tags, checklist note",
            "details": _TRIP_OVERVIEW + " Passing tags replaces the whole tag list. Changing the dates does not retag existing expenses; use apply_tags.",
            "aliases": ["/tripupdate"],
            "flags": {**TRIP_FLAGS, "--name": "name"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a trip and its legs; its stays and visits are kept (detached) with their notes and grades",
            "aliases": ["/tripdelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "costs": {
            "description": "Cost of a trip by ID: total (each charge once), by kind and per leg / stay / visit",
            "details": "Derived from linked finance transactions in EUR; transactions without an EUR amount are counted as unconverted, never as zero.",
            "aliases": ["/tripcosts"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "recap": {
            "description": "Recap of a trip (by id or name): spend, days, cities, visits done and missed, highlights and what is still to grade",
            "details": "Meant for after the trip. to_complete lists visited visits and stays that still lack a grade or notes; spend is derived from linked transactions.",
            "aliases": ["/triprecap"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["trip"],
        },
        "today": {
            "description": "What matters now on an ongoing trip: the next step with a countdown and today's visits to mark",
            "details": "The trip argument is an id or name; omit it for the ongoing trip. Use travel_visit update to mark a visit visited or missed.",
            "aliases": ["/today"],
            "flags": {},
            "arg_keys": ["trip"],
        },
        "apply_tags": {
            "description": "Tag the expenses already dated within a trip with the trip's finance tags",
            "details": "New expenses (manual or imported) pick the tags up on their own; use this after changing the dates or the finance tags. Only expenses are tagged.",
            "aliases": ["/tripapplytags"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "travel_leg": {
        "add": {
            "description": "Add a leg to a trip: trip id, then mode; --from/--to, --departs/--arrives with --departs-tz/--arrives-tz",
            "details": _LEG_OVERVIEW,
            "aliases": ["/legadd"],
            "flags": LEG_FLAGS,
            "requires_args": True,
            "arg_keys": ["trip_id", "mode"],
        },
        "update": {
            "description": "Update a leg by ID (mode, origin, destination, times, carrier, number, booking ref, seat, notes)",
            "details": _LEG_OVERVIEW,
            "aliases": ["/legupdate"],
            "flags": {**LEG_FLAGS, "--mode": "mode"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a leg by ID",
            "aliases": ["/legdelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "link": {
            "description": "Link a finance transaction to a leg (a ticket, seat, baggage or change fee)",
            "details": _TRAVEL_LINK_DETAILS,
            "aliases": ["/leglink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
        },
        "unlink": {
            "description": "Unlink a finance transaction from a leg",
            "aliases": ["/legunlink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
        },
    },
    "travel_stay": {
        "add": {
            "description": "Add a stay: --place id or --hotel name, --check-in/--check-out with --tz; trip id as the argument",
            "details": _STAY_OVERVIEW,
            "aliases": ["/stayadd"],
            "flags": STAY_FLAGS,
            "arg_keys": ["trip_id"],
        },
        "update": {
            "description": "Update a stay by ID (place, times, zone, booking ref, notes, grade, trip)",
            "details": _STAY_OVERVIEW,
            "aliases": ["/stayupdate"],
            "flags": STAY_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a stay by ID",
            "aliases": ["/staydelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "link": {
            "description": "Link a finance transaction to a stay (deposit, balance, city tax)",
            "details": _TRAVEL_LINK_DETAILS,
            "aliases": ["/staylink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
        },
        "unlink": {
            "description": "Unlink a finance transaction from a stay",
            "aliases": ["/stayunlink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
        },
    },
    "travel_place": {
        "add": {
            "description": "Add a place: name, then --kind (hotel, restaurant, cafe, activity, museum, attraction, shop, other), city, country",
            "details": _PLACE_OVERVIEW,
            "aliases": ["/placeadd"],
            "flags": PLACE_FLAGS,
            "requires_args": True,
            "arg_keys": ["name"],
        },
        "list": {
            "description": "List places; the argument searches name, city and address. Filter by kind, city, tag, min grade, visit status",
            "details": _PLACE_OVERVIEW + " no_trip=true keeps only places that belong to no trip. Each place carries its derived grade.",
            "aliases": ["/places", "/placelist"],
            "flags": PLACE_LIST_FLAGS,
            "arg_keys": ["q"],
        },
        "get": {
            "description": "Show a place (by id or name) with its visit and stay history, derived grade and lifetime cost",
            "aliases": ["/place", "/placeget"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["place"],
        },
        "update": {
            "description": "Update a place by ID (name, kind, city, country, maps link, coordinates, address, notes, tags)",
            "details": _PLACE_OVERVIEW + " Passing tags replaces the whole tag list.",
            "aliases": ["/placeupdate"],
            "flags": {**PLACE_FLAGS, "--name": "name"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a place by ID; refused while it has visits or stays",
            "aliases": ["/placedelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
    },
    "travel_visit": {
        "add": {
            "description": "Plan or log a visit: place id or name, then --trip, --date, --time, --status, --grade, --notes",
            "details": _VISIT_OVERVIEW,
            "aliases": ["/visitadd"],
            "flags": VISIT_FLAGS,
            "requires_args": True,
            "arg_keys": ["place"],
        },
        "note": {
            "description": "Add a timestamped note to the latest visit of the ongoing trip that has already started",
            "details": "Appends '[date HH:MM] text' to that visit's notes. Older visits are edited with update. Nothing is written when no visit has started yet.",
            "aliases": ["/tnote"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["text"],
        },
        "list": {
            "description": "List visits, optionally for a trip, a place or a status; --no-trip true for the wishlist and home-city visits",
            "details": _VISIT_OVERVIEW,
            "aliases": ["/visits", "/visitlist"],
            "flags": VISIT_LIST_FLAGS,
        },
        "update": {
            "description": "Update a visit by ID (status, day, time, grade, notes, trip, place)",
            "details": _VISIT_OVERVIEW + " Moving a graded visit back to planned or missed drops its grade.",
            "aliases": ["/visitupdate"],
            "flags": VISIT_FLAGS,
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "visited": {
            "description": "Mark a visit as visited, optionally with --grade 1-5 and --notes",
            "aliases": ["/visited"],
            "flags": {"--grade": "grade", "--notes": "notes", "--date": "date"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "missed": {
            "description": "Mark a planned visit as missed, optionally with --notes",
            "aliases": ["/missed"],
            "flags": {"--notes": "notes"},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "delete": {
            "description": "Delete a visit by ID",
            "aliases": ["/visitdelete"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id"],
        },
        "link": {
            "description": "Link a finance transaction to a visit (a meal, an entry fee)",
            "details": _TRAVEL_LINK_DETAILS,
            "aliases": ["/visitlink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
        },
        "unlink": {
            "description": "Unlink a finance transaction from a visit",
            "aliases": ["/visitunlink"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["id", "transaction_id"],
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
        "miss": {
            "description": "Mark a block of a date's saved plan as not done (the task stays open and can be planned again)",
            "details": _DAY_PLAN_MISS_DETAILS,
            "aliases": ["/dayplanmiss"],
            "flags": {"--ref": "ref_id", "--kind": "kind", "--title": "title", "--start": "start"},
            "requires_args": True,
            "arg_keys": ["date"],
        },
        "done": {
            "description": "Mark a block of a date's saved plan as done (distinguishes done from never marked)",
            "details": _DAY_PLAN_MISS_DETAILS,
            "aliases": ["/dayplandone"],
            "flags": {"--ref": "ref_id", "--kind": "kind", "--title": "title", "--start": "start"},
            "requires_args": True,
            "arg_keys": ["date"],
        },
        "undone": {
            "description": "Undo a done mark on a block of a date's saved plan",
            "details": _DAY_PLAN_MISS_DETAILS,
            "aliases": ["/dayplanundone"],
            "flags": {"--ref": "ref_id", "--kind": "kind", "--title": "title", "--start": "start"},
            "requires_args": True,
            "arg_keys": ["date"],
        },
        "edit": {
            "description": "Replace the blocks in a time slice of already saved days without resending the whole days",
            "details": _DAY_PLAN_EDIT_DETAILS,
            "aliases": ["/dayplanedit"],
            "flags": {},
            "requires_args": True,
            "arg_keys": ["days"],
        },
        "review": {
            "description": "Per item: how many times it was planned, done, missed or left unmarked over a week",
            "details": _DAY_PLAN_REVIEW_DETAILS,
            "aliases": ["/dayplanreview"],
            "flags": {"--to": "to"},
            "requires_args": True,
            "arg_keys": ["from"],
        },
        "unmiss": {
            "description": "Undo a not-done mark on a block of a date's saved plan",
            "details": _DAY_PLAN_MISS_DETAILS,
            "aliases": ["/dayplanunmiss"],
            "flags": {"--ref": "ref_id", "--kind": "kind", "--title": "title", "--start": "start"},
            "requires_args": True,
            "arg_keys": ["date"],
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
