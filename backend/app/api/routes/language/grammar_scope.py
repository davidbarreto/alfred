from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import GrammarScopeServiceDep
from app.features.language.grammar_scope.schemas import (
    GrammarScopeCreate,
    GrammarScopeFilters,
    GrammarScopeRead,
    GrammarScopeUpdate,
)

router = APIRouter(prefix="/language/grammar-scope", tags=["language"], dependencies=[Depends(require_auth)])


@router.post("", response_model=GrammarScopeRead, status_code=status.HTTP_201_CREATED)
async def create_scope(request: GrammarScopeCreate, service: GrammarScopeServiceDep):
    return await service.create_scope(request)


@router.post("/bulk", response_model=list[GrammarScopeRead], status_code=status.HTTP_201_CREATED)
async def bulk_create_scopes(request: list[GrammarScopeCreate], service: GrammarScopeServiceDep):
    return await service.bulk_create_scopes(request)


@router.get("", response_model=list[GrammarScopeRead])
async def get_scopes(service: GrammarScopeServiceDep, filters: GrammarScopeFilters = Depends()):
    return await service.get_scopes(filters)


@router.get("/{scope_id}", response_model=GrammarScopeRead)
async def get_scope(scope_id: int, service: GrammarScopeServiceDep):
    scope = await service.get_scope(scope_id)
    if scope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grammar scope not found")
    return scope


@router.patch("/{scope_id}", response_model=GrammarScopeRead)
async def update_scope(scope_id: int, request: GrammarScopeUpdate, service: GrammarScopeServiceDep):
    scope = await service.update_scope(scope_id, request)
    if scope is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grammar scope not found")
    return scope


@router.delete("/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope(scope_id: int, service: GrammarScopeServiceDep):
    await service.delete_scope(scope_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
