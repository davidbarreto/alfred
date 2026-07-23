from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ShoppingCategoryServiceDep
from app.features.organizer.shopping_categories.schemas import (
    ShoppingCategoryCreate,
    ShoppingCategoryRead,
    ShoppingCategoryUpdate,
)
from app.features.organizer.shopping_categories.service import ShoppingCategoryDeletionBlockedError

router = APIRouter(prefix="/organizer/shopping-categories", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.post("", response_model=ShoppingCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_category(request: ShoppingCategoryCreate, service: ShoppingCategoryServiceDep):
    return await service.create(request)


@router.get("", response_model=list[ShoppingCategoryRead])
async def list_shopping_categories(service: ShoppingCategoryServiceDep):
    return await service.list()


@router.get("/{category_id}", response_model=ShoppingCategoryRead)
async def get_shopping_category(category_id: int, service: ShoppingCategoryServiceDep):
    category = await service.get(category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping category not found")
    return category


@router.patch("/{category_id}", response_model=ShoppingCategoryRead)
async def update_shopping_category(category_id: int, request: ShoppingCategoryUpdate, service: ShoppingCategoryServiceDep):
    category = await service.update(category_id, request)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping category not found")
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_category(category_id: int, service: ShoppingCategoryServiceDep):
    try:
        deleted = await service.delete(category_id)
    except ShoppingCategoryDeletionBlockedError as exc:
        detail = (
            f"Cannot delete this category: it still has {exc.shopping_count} shopping item(s), "
            f"{exc.wishlist_count} wishlist item(s), and {exc.recurrence_count} recurring item(s). "
            "Reassign or delete those items first."
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping category not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
