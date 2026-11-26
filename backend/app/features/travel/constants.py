"""Enum value sets for the travel module, defined once and shared by Pydantic, CHECK constraints and MCP descriptions."""
from typing import Literal, TypeAlias

LEG_MODES = ("flight", "train", "bus", "ferry", "car", "other")
LegMode: TypeAlias = Literal["flight", "train", "bus", "ferry", "car", "other"]

VISIT_STATUSES = ("planned", "visited", "missed")
VisitStatus: TypeAlias = Literal["planned", "visited", "missed"]

# A place's travel status (docs/modules/places.md): visited wins over planned.
PlaceStatus: TypeAlias = Literal["visited", "planned"]
# A city's, best first: the home city, a past home (Places lived), something visited, something ahead, only a leg end,
# only links.
CITY_STATUSES = ("home", "lived", "visited", "planned", "passed", "none")
CityStatus: TypeAlias = Literal["home", "lived", "visited", "planned", "passed", "none"]
# The Cities and Countries filter: each choice and the statuses it shows.
CITY_STATUS_GROUPS: dict[str, frozenset[str]] = {
    "visited": frozenset({"home", "lived", "visited"}), "planned": frozenset({"planned"}), "passed": frozenset({"passed"}),
}
CityStatusFilter: TypeAlias = Literal["visited", "planned", "passed", "all"]

WEB_LINK_KINDS = ("website", "instagram", "tiktok", "video", "article", "map", "booking", "other")
WebLinkKind: TypeAlias = Literal["website", "instagram", "tiktok", "video", "article", "map", "booking", "other"]

TRIP_STATUS_FILTERS = ("current", "upcoming", "ongoing", "past", "all")
TripStatusFilter: TypeAlias = Literal["current", "upcoming", "ongoing", "past", "all"]


def in_clause(column: str, values: tuple[str, ...]) -> str:
    """SQL text for a CHECK constraint restricting `column` to `values`."""
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))
