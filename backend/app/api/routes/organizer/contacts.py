from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import ContactsCRUDServiceDep
from app.features.organizer.contacts.schemas import (
    ContactCreate,
    ContactFilters,
    ContactRead,
    ContactUpdate,
)

router = APIRouter(
    prefix="/organizer/contacts",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("/", response_model=list[ContactRead])
async def get_contacts(
    service: ContactsCRUDServiceDep,
    filters: ContactFilters = Depends(),
) -> list[ContactRead]:
    return await service.get_contacts(filters)


@router.get("/{contact_id}", response_model=ContactRead)
async def get_contact(contact_id: int, service: ContactsCRUDServiceDep) -> ContactRead:
    contact = await service.get_contact(contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.post("/", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
async def create_contact(request: ContactCreate, service: ContactsCRUDServiceDep) -> ContactRead:
    return await service.create_contact(request)


@router.patch("/{contact_id}", response_model=ContactRead)
async def update_contact(
    contact_id: int,
    request: ContactUpdate,
    service: ContactsCRUDServiceDep,
) -> ContactRead:
    contact = await service.update_contact(contact_id, request)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: int, service: ContactsCRUDServiceDep) -> Response:
    await service.delete_contact(contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
