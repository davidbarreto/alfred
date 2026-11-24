from typing import Literal, get_args

# Location kinds. Defined once: the schema Literal, the DB CHECK constraint, the filters and the MCP
# descriptions all come from here, so clients can look a place up by kind (the office is kind "work").
LocationKind = Literal[
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
    "other",
]
LOCATION_KINDS: tuple[str, ...] = get_args(LocationKind)
HOME_KIND = "home"
DEFAULT_KIND = "other"
