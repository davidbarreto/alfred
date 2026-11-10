"""Enum value sets for the travel module, defined once and shared by Pydantic, CHECK constraints and MCP descriptions."""
from typing import Literal, TypeAlias

PLACE_KINDS = ("hotel", "restaurant", "cafe", "activity", "museum", "attraction", "shop", "other")
PlaceKind: TypeAlias = Literal["hotel", "restaurant", "cafe", "activity", "museum", "attraction", "shop", "other"]

LEG_MODES = ("flight", "train", "bus", "ferry", "car", "other")
LegMode: TypeAlias = Literal["flight", "train", "bus", "ferry", "car", "other"]

VISIT_STATUSES = ("planned", "visited", "missed")
VisitStatus: TypeAlias = Literal["planned", "visited", "missed"]

TRIP_STATUS_FILTERS = ("current", "upcoming", "ongoing", "past", "all")
TripStatusFilter: TypeAlias = Literal["current", "upcoming", "ongoing", "past", "all"]


def in_clause(column: str, values: tuple[str, ...]) -> str:
    """SQL text for a CHECK constraint restricting `column` to `values`."""
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))
