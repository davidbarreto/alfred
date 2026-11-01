from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ShoppingProductServiceDep
from app.features.organizer.shopping_products.schemas import (
    ShoppingProductCreate,
    ShoppingProductFilters,
    ShoppingProductMerge,
    ShoppingProductRead,
    ShoppingProductUpdate,
)

router = APIRouter(prefix="/organizer/shopping-products", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[ShoppingProductRead])
async def list_shopping_products(service: ShoppingProductServiceDep, filters: ShoppingProductFilters = Depends()):
    return await service.list(filters)


@router.post("", response_model=ShoppingProductRead, status_code=status.HTTP_201_CREATED)
async def create_shopping_product(request: ShoppingProductCreate, service: ShoppingProductServiceDep):
    return await service.create(request)


@router.get("/{product_id}", response_model=ShoppingProductRead)
async def get_shopping_product(product_id: int, service: ShoppingProductServiceDep):
    product = await service.get(product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping product not found")
    return product


@router.patch("/{product_id}", response_model=ShoppingProductRead)
async def update_shopping_product(product_id: int, request: ShoppingProductUpdate, service: ShoppingProductServiceDep):
    product = await service.update(product_id, request)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping product not found")
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_product(product_id: int, service: ShoppingProductServiceDep):
    if not await service.delete(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping product not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/merge", response_model=ShoppingProductRead)
async def merge_shopping_product(product_id: int, request: ShoppingProductMerge, service: ShoppingProductServiceDep):
    product = await service.merge(product_id, request.into_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping product not found")
    return product
