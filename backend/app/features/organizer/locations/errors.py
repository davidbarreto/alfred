from __future__ import annotations


class LocationConflictError(Exception):
    """A second home, or a name another location already has (409)."""


class LocationValidationError(ValueError):
    """Input the schema can't check alone: opening hours that don't parse, unknown categories (422)."""
