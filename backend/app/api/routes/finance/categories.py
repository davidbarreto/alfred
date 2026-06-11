from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import CategoryServiceDep
from app.features.finance.categories.schemas import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/finance/categories", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("/", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(request: CategoryCreate, service: CategoryServiceDep):
    return await service.create(request)


@router.get("/", response_model=list[CategoryRead])
async def list_categories(service: CategoryServiceDep):
    return await service.list()


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(category_id: int, service: CategoryServiceDep):
    category = await service.get(category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(category_id: int, request: CategoryUpdate, service: CategoryServiceDep):
    category = await service.update(category_id, request)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, service: CategoryServiceDep):
    deleted = await service.delete(category_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
