# Planning vocabularies for calendar events. Defined once: the schema Literals, the DB CHECK
# constraints and the MCP tool descriptions are all derived from these tuples.
EVENT_AVAILABILITIES = ("blocked", "light", "free")
EVENT_PRESENCES = ("in_person", "remote_home", "remote_anywhere")


def effective_availability(availability: str | None, all_day: bool) -> str:
    """NULL availability means the default: all-day events are free, timed ones are blocked."""
    if availability is not None:
        return availability
    return "free" if all_day else "blocked"
