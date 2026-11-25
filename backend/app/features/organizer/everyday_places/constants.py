from app.features.location.places.constants import PLACE_KINDS

# Whether a new place of a kind is one of the everyday places when the user doesn't say. Kinds in neither set
# (a restaurant, a cafe, a park...) can be either, so the `place add` command asks.
EVERYDAY_KINDS = frozenset({
    "home", "work", "school", "gym", "sports", "supermarket", "pharmacy", "bakery", "market", "mall",
    "variety_store", "hardware_store", "health", "playground",
})
TRIP_KINDS = frozenset({"hotel", "activity", "museum", "attraction"})

assert EVERYDAY_KINDS.isdisjoint(TRIP_KINDS) and (EVERYDAY_KINDS | TRIP_KINDS) <= set(PLACE_KINDS)


def default_everyday(kind: str) -> bool | None:
    """True or False when the kind decides it, None when the user has to be asked."""
    if kind in EVERYDAY_KINDS:
        return True
    if kind in TRIP_KINDS:
        return False
    return None
