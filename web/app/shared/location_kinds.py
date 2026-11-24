# The backend's fixed location kinds (LOCATION_KINDS); the API refuses any other value.
# Each maps to the Tabler icon the portal shows next to a location of that kind.
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
    "other": "ti-map-pin",
}
KINDS = tuple(KIND_ICONS)


def location_icon(kind: str | None) -> str:
    """The Tabler icon class for a location kind; the generic pin for an unknown one."""
    return KIND_ICONS.get(kind or "", KIND_ICONS["other"])
