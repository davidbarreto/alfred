class TravelNotFoundError(Exception):
    """A referenced trip, place or stay does not exist."""


class TravelConflictError(Exception):
    """The request clashes with existing data (e.g. a calendar event already imported)."""
