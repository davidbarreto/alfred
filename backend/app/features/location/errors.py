class LocationNotFoundError(Exception):
    """A referenced country, city or place does not exist."""


class LocationConflictError(Exception):
    """The request clashes with existing data (a taken name, a second home, a city or place still in use)."""


class LocationValidationError(ValueError):
    """Input the schema can't check alone: opening hours that don't parse, no city and no Home to default to (422)."""
