class LocationNotFoundError(Exception):
    """A referenced country, city or place does not exist."""


class LocationConflictError(Exception):
    """The request clashes with existing data (a taken name, a city still in use)."""
