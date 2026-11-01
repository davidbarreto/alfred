from __future__ import annotations


class ShoppingItemAlreadyPendingError(Exception):
    """Raised when a product already has a pending entry on the shopping list."""

    def __init__(self, name: str, item_id: int | None = None) -> None:
        self.name = name
        self.item_id = item_id
        suffix = f" (item {item_id})" if item_id is not None else ""
        super().__init__(f"{name!r} is already on the shopping list{suffix}")


class ShoppingProductNameTakenError(Exception):
    """Raised when a product is created or renamed to a name another product already has."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A product named {name!r} already exists")


class ShoppingProductBlockedError(Exception):
    """Raised when a product can't be deleted or merged because of pending list entries."""
