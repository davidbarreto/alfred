from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.auth import require_auth
from app.dependencies import ShoppingServiceDep
from app.features.organizer.shopping.schemas import (
    FrequentItemFilters,
    FrequentItemRead,
    RecurrenceItemCreate,
    RecurrenceItemRead,
    RecurrenceItemUpdate,
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemRead,
    ShoppingItemUpdate,
    ShoppingPriority,
    WishlistItemCreate,
    WishlistItemFilters,
    WishlistItemRead,
    WishlistItemUpdate,
)

_auth = [Depends(require_auth)]

shopping_router = APIRouter(prefix="/organizer/shopping", tags=["organizer"], dependencies=_auth)
wishlist_router = APIRouter(prefix="/organizer/wishlist", tags=["organizer"], dependencies=_auth)
recurrence_router = APIRouter(prefix="/organizer/recurrence", tags=["organizer"], dependencies=_auth)


# --- Shopping items ---

@shopping_router.get("", response_model=list[ShoppingItemRead])
async def list_shopping_items(service: ShoppingServiceDep, filters: ShoppingItemFilters = Depends()):
    return await service.list_items(filters)


@shopping_router.post("", response_model=ShoppingItemRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_item(request: ShoppingItemCreate, service: ShoppingServiceDep):
    return await service.create_item(request)


@shopping_router.get("/frequent", response_model=list[FrequentItemRead])
async def list_frequent_shopping_items(service: ShoppingServiceDep, filters: FrequentItemFilters = Depends()):
    return await service.list_frequent_items(filters)


@shopping_router.get("/{item_id}", response_model=ShoppingItemRead)
async def get_shopping_item(item_id: int, service: ShoppingServiceDep):
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping item not found")
    return item


@shopping_router.patch("/{item_id}", response_model=ShoppingItemRead)
async def update_shopping_item(item_id: int, request: ShoppingItemUpdate, service: ShoppingServiceDep):
    item = await service.update_item(item_id, request)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping item not found")
    return item


@shopping_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_item(item_id: int, service: ShoppingServiceDep):
    await service.delete_item(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@shopping_router.post("/{item_id}/bought", response_model=ShoppingItemRead)
async def mark_shopping_item_bought(item_id: int, service: ShoppingServiceDep):
    item = await service.mark_bought(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping item not found")
    return item


@shopping_router.post("/{item_id}/skipped", response_model=ShoppingItemRead)
async def mark_shopping_item_skipped(item_id: int, service: ShoppingServiceDep):
    item = await service.mark_skipped(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping item not found")
    return item


# --- Wishlist items ---

@wishlist_router.get("", response_model=list[WishlistItemRead])
async def list_wishlist_items(service: ShoppingServiceDep, filters: WishlistItemFilters = Depends()):
    return await service.list_wishes(filters)


@wishlist_router.post("", response_model=WishlistItemRead, status_code=status.HTTP_201_CREATED)
async def create_wishlist_item(request: WishlistItemCreate, service: ShoppingServiceDep):
    return await service.create_wish(request)


@wishlist_router.get("/{item_id}", response_model=WishlistItemRead)
async def get_wishlist_item(item_id: int, service: ShoppingServiceDep):
    item = await service.get_wish(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found")
    return item


@wishlist_router.patch("/{item_id}", response_model=WishlistItemRead)
async def update_wishlist_item(item_id: int, request: WishlistItemUpdate, service: ShoppingServiceDep):
    item = await service.update_wish(item_id, request)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found")
    return item


@wishlist_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist_item(item_id: int, service: ShoppingServiceDep):
    await service.delete_wish(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class _PromoteRequest(BaseModel):
    priority: ShoppingPriority = "want"


@wishlist_router.post("/{item_id}/promote", response_model=ShoppingItemRead)
async def promote_wishlist_item(item_id: int, request: _PromoteRequest, service: ShoppingServiceDep):
    item = await service.promote_wish(item_id, priority=request.priority)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found")
    return item


# --- Recurrence items ---

@recurrence_router.get("", response_model=list[RecurrenceItemRead])
async def list_recurrence_items(service: ShoppingServiceDep, active_only: bool = True):
    return await service.list_recurrences(active_only=active_only)


@recurrence_router.post("", response_model=RecurrenceItemRead, status_code=status.HTTP_201_CREATED)
async def create_recurrence_item(request: RecurrenceItemCreate, service: ShoppingServiceDep):
    return await service.create_recurrence(request)


@recurrence_router.get("/{item_id}", response_model=RecurrenceItemRead)
async def get_recurrence_item(item_id: int, service: ShoppingServiceDep):
    item = await service.get_recurrence(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurrence item not found")
    return item


@recurrence_router.patch("/{item_id}", response_model=RecurrenceItemRead)
async def update_recurrence_item(item_id: int, request: RecurrenceItemUpdate, service: ShoppingServiceDep):
    item = await service.update_recurrence(item_id, request)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurrence item not found")
    return item


@recurrence_router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurrence_item(item_id: int, service: ShoppingServiceDep):
    await service.delete_recurrence(item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
