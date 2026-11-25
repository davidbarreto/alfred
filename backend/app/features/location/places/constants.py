from typing import Literal, get_args

# Place kinds: everyday ones and trip ones in one list. Defined once: the schema Literal, the DB CHECK constraint,
# the filters and the MCP descriptions all come from here, so clients can look a place up by kind (the office is
# kind "work").
PlaceKind = Literal[
    "home",
    "work",  # the office or workplace
    "school",  # also classes and courses
    "gym",
    "sports",  # pool, pitch, club
    "supermarket",
    "pharmacy",
    "bakery",
    "market",
    "mall",  # shopping centre
    "variety_store",  # bazaar-style shop with a bit of everything: household goods, tools, gear
    "hardware_store",  # DIY and tools
    "shop",  # any other shop
    "restaurant",
    "cafe",
    "health",  # doctor, dentist, clinic, hospital
    "park",
    "playground",  # also indoor play centres for kids
    "venue",  # concerts, theatre, cinema
    "hotel",  # any stay: hotel, flat, hostel
    "activity",  # a tour, a class, an experience
    "museum",
    "attraction",  # a sight, a viewpoint, a monument
    "other",
]
PLACE_KINDS: tuple[str, ...] = get_args(PlaceKind)
HOME_KIND = "home"
DEFAULT_KIND = "other"


def kind_check(column: str = "kind") -> str:
    """SQL text for the CHECK constraint restricting `column` to PLACE_KINDS."""
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in PLACE_KINDS))
