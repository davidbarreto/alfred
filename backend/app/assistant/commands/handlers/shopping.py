from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.shopping.schemas import (
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemUpdate,
    WishlistItemCreate,
    WishlistItemFilters,
    WishlistItemUpdate,
)
from app.features.organizer.shopping.service import ShoppingService

logger = logging.getLogger(__name__)


async def handle_shopping(cmd_type: str, command: str, arguments: dict[str, Any], service: ShoppingService) -> Any:
    logger.debug("handle_shopping: type=%s command=%s args_keys=%s", cmd_type, command, list(arguments.keys()))

    if cmd_type == "shopping":
        if command == "add":
            quantity = arguments.get("quantity")
            estimated_price_raw = arguments.get("estimated_price")
            payload = ShoppingItemCreate(
                name=arguments.get("name", ""),
                category=arguments.get("category", "other"),
                priority=arguments.get("priority", "need"),
                quantity=float(quantity) if quantity else None,
                unit=arguments.get("unit"),
                store=arguments.get("store"),
                estimated_price=float(estimated_price_raw) if estimated_price_raw else None,
                notes=arguments.get("notes"),
            )
            result = await service.create_item(payload)
            return result.model_dump()

        if command == "list":
            filters = ShoppingItemFilters(
                status=arguments.get("status", "pending"),
                category=arguments.get("category", "all"),
                priority=arguments.get("priority", "all"),
                limit=int(arguments.get("limit", 100)),
            )
            results = await service.list_items(filters)
            return [r.model_dump() for r in results]

        if command == "complete":
            item = await _resolve_shopping_item(arguments, service)
            result = await service.mark_bought(item.id)
            return result.model_dump()

        if command == "delete":
            item = await _resolve_shopping_item(arguments, service)
            await service.delete_item(item.id)
            return {"deleted": True, "id": item.id}

        if command == "update":
            item_id = int(arguments["id"])
            fields: dict[str, Any] = {}
            if "name" in arguments:
                fields["name"] = arguments["name"]
            if "category" in arguments:
                fields["category"] = arguments["category"]
            if "priority" in arguments:
                fields["priority"] = arguments["priority"]
            if "status" in arguments:
                fields["status"] = arguments["status"]
            if "quantity" in arguments:
                fields["quantity"] = float(arguments["quantity"]) if arguments["quantity"] else None
            result = await service.update_item(item_id, ShoppingItemUpdate(**fields))
            if result is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shopping item {item_id} not found")
            return result.model_dump()

    if cmd_type == "wishlist":
        if command == "add":
            estimated_price_raw = arguments.get("estimated_price")
            payload = WishlistItemCreate(
                name=arguments.get("name", ""),
                category=arguments.get("category", "other"),
                estimated_price=float(estimated_price_raw) if estimated_price_raw else None,
                url=arguments.get("url"),
                notes=arguments.get("notes"),
            )
            result = await service.create_wish(payload)
            return result.model_dump()

        if command == "list":
            filters = WishlistItemFilters(
                category=arguments.get("category", "all"),
                limit=int(arguments.get("limit", 100)),
            )
            results = await service.list_wishes(filters)
            return [r.model_dump() for r in results]

        if command == "delete":
            wish = await _resolve_wishlist_item(arguments, service)
            await service.delete_wish(wish.id)
            return {"deleted": True, "id": wish.id}

        if command == "promote":
            wish = await _resolve_wishlist_item(arguments, service)
            priority = arguments.get("priority", "want")
            result = await service.promote_wish(wish.id, priority=priority)
            return result.model_dump()

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown shopping command: {cmd_type}.{command}",
    )


async def _resolve_shopping_item(arguments: dict[str, Any], service: ShoppingService):
    if "id" in arguments and arguments["id"] is not None:
        item = await service.get_item(int(arguments["id"]))
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Shopping item {arguments['id']} not found")
        return item
    if "name" in arguments and arguments["name"]:
        items = await service.list_items(ShoppingItemFilters(status="pending", limit=100))
        name_lower = arguments["name"].lower()
        match = next((i for i in items if i.name.lower() == name_lower), None)
        if match is None:
            match = next((i for i in items if name_lower in i.name.lower()), None)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No pending shopping item matching '{arguments['name']}'")
        return match
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shopping item id or name is required")


async def _resolve_wishlist_item(arguments: dict[str, Any], service: ShoppingService):
    if "id" in arguments and arguments["id"] is not None:
        item = await service.get_wish(int(arguments["id"]))
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Wishlist item {arguments['id']} not found")
        return item
    if "name" in arguments and arguments["name"]:
        items = await service.list_wishes(WishlistItemFilters(limit=200))
        name_lower = arguments["name"].lower()
        match = next((i for i in items if i.name.lower() == name_lower), None)
        if match is None:
            match = next((i for i in items if name_lower in i.name.lower()), None)
        if match is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No wishlist item matching '{arguments['name']}'")
        return match
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Wishlist item id or name is required")
