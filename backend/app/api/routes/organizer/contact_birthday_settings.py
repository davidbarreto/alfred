from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ContactBirthdaySettingsServiceDep
from app.features.organizer.contacts.notification_settings.schemas import (
    ContactBirthdayCascadeUpdate,
    ContactBirthdayCascadesRead,
)

router = APIRouter(
    prefix="/organizer/contact-birthday-settings", tags=["organizer"], dependencies=[Depends(require_auth)]
)


@router.get("", response_model=ContactBirthdayCascadesRead)
async def get_contact_birthday_settings(service: ContactBirthdaySettingsServiceDep):
    return await service.get()


@router.put("/{relationship}", response_model=ContactBirthdayCascadesRead)
async def update_contact_birthday_cascade(
    relationship: str, request: ContactBirthdayCascadeUpdate, service: ContactBirthdaySettingsServiceDep
):
    return await service.update_relationship(relationship, request)
