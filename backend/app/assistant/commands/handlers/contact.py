import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.contacts.schemas import ContactFilters
from app.features.organizer.contacts.service import ContactService

logger = logging.getLogger(__name__)


async def handle_contact(command: str, arguments: dict[str, Any], service: ContactService) -> Any:
    logger.debug("handle_contact: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "list":
        filters = ContactFilters(
            limit=int(arguments.get("limit", 100)),
            offset=int(arguments.get("offset", 0)),
            name=None,
            email=None,
            letter=None,
            has_birthday=None,
            relationship=arguments.get("relationship"),
        )
        results = await service.get_contacts(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "search":
        filters = ContactFilters(
            limit=int(arguments.get("limit", 100)),
            offset=int(arguments.get("offset", 0)),
            name=arguments.get("query"),
            email=None,
            letter=None,
            has_birthday=None,
            relationship=None,
        )
        results = await service.get_contacts(filters)
        return [r.model_dump(mode="json") for r in results]

    if command == "get":
        contact_id = int(arguments["id"])
        result = await service.get_contact(contact_id)
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Contact {contact_id} not found")
        return result.model_dump(mode="json")

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown contact command: {command}")
