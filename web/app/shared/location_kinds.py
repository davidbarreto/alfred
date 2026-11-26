# The backend's fixed place kinds (PLACE_KINDS, in its order); the API refuses any other value.
# Each maps to the Tabler icon the portal shows next to a place of that kind.
KIND_ICONS = {
    "home": "ti-home",
    "work": "ti-briefcase",
    "school": "ti-school",
    "gym": "ti-barbell",
    "sports": "ti-ball-football",
    "supermarket": "ti-shopping-cart",
    "pharmacy": "ti-pill",
    "bakery": "ti-bread",
    "market": "ti-basket",
    "mall": "ti-shopping-bag",
    "variety_store": "ti-packages",
    "hardware_store": "ti-tool",
    "shop": "ti-building-store",
    "restaurant": "ti-tools-kitchen-2",
    "cafe": "ti-coffee",
    "health": "ti-stethoscope",
    "park": "ti-trees",
    "playground": "ti-horse-toy",
    "venue": "ti-ticket",
    "hotel": "ti-bed",
    "activity": "ti-route",
    "museum": "ti-building-bank",
    "attraction": "ti-camera",
    "other": "ti-map-pin",
}
KINDS = tuple(KIND_ICONS)

# Copies of the backend's organizer/everyday_places/constants.py: whether a new place of a kind is everyday when the
# user doesn't say (the new-place form pre-ticks Everyday from them; kinds in neither set start unticked).
EVERYDAY_KINDS = frozenset({
    "home", "work", "school", "gym", "sports", "supermarket", "pharmacy", "bakery", "market", "mall",
    "variety_store", "hardware_store", "health", "playground",
})
TRIP_KINDS = frozenset({"hotel", "activity", "museum", "attraction"})
# What the calendar's "+ New place" (always an everyday place) offers: every kind but home and the trip-only ones.
EVERYDAY_PICK_KINDS = tuple(k for k in KINDS if k != "home" and k not in TRIP_KINDS)


def location_icon(kind: str | None) -> str:
    """The Tabler icon class for a place kind; the generic pin for an unknown one."""
    return KIND_ICONS.get(kind or "", KIND_ICONS["other"])

# The map pin's colour group per kind (pins are coloured by group, iconed by kind); kinds not listed are "everyday".
KIND_GROUPS = {
    "home": "home",
    "hotel": "stay",
    "restaurant": "food", "cafe": "food", "bakery": "food",
    "museum": "sight", "attraction": "sight", "activity": "sight", "venue": "sight", "park": "sight",
    "playground": "sight", "sports": "sight",
}
MAP_GROUP_LABELS = {"stay": "Stays", "food": "Food and drink", "sight": "Sights and activities", "everyday": "Everyday"}
# The map's status toggles, in their order: visited (home, lived, visited) solid, passed through small and grey, planned
# hollow. Only Visited is on when a map opens.
MAP_STATUS_LABELS = {"visited": "Visited", "passed": "Passed through", "planned": "Planned"}


def map_group(kind: str | None) -> str:
    return KIND_GROUPS.get(kind or "", "everyday")
