import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import parse_tags
from app.features.organizer.notes.schemas import NoteCreate, NoteFilters, NoteUpdate
from app.features.organizer.notes.service import NoteService

logger = logging.getLogger(__name__)

_TITLE_MAX = 60


def _derive_note_fields(title_raw: str | None, content_raw: str | None) -> tuple[str, str]:
    if not content_raw:
        content_raw = title_raw or ""
    if not title_raw:
        title_raw = content_raw
    title = title_raw if len(title_raw) <= _TITLE_MAX else title_raw[:_TITLE_MAX].rstrip() + "…"
    return title, content_raw


async def handle_note(command: str, arguments: dict[str, Any], service: NoteService) -> Any:
    logger.debug("handle_note: command=%s args_keys=%s", command, list(arguments.keys()))
    if command == "add":
        title, content = _derive_note_fields(
            arguments.get("title"),
            arguments.get("content"),
        )
        payload = NoteCreate(
            title=title,
            content=content,
            tags=parse_tags(arguments.get("tags")),
        )
        result = await service.create_note(payload)
        return result.model_dump()

    if command == "list":
        filters = NoteFilters(
            limit=int(arguments.get("limit", 100)),
            tags=parse_tags(arguments.get("tags")) or None,
        )
        results = await service.get_notes(filters)
        return [r.model_dump() for r in results]

    if command == "search":
        query = str(arguments.get("query", "")).lower()
        all_notes = await service.get_notes(NoteFilters(limit=200))
        filtered = [
            n for n in all_notes
            if query in n.title.lower() or query in (n.content or "").lower()
        ]
        return [n.model_dump() for n in filtered]

    if command == "update":
        note_id = int(arguments["id"])
        update_fields: dict[str, Any] = {}
        if "title" in arguments:
            update_fields["title"] = arguments["title"]
        if "content" in arguments:
            update_fields["content"] = arguments["content"]
        if "tags" in arguments:
            update_fields["tags"] = parse_tags(arguments["tags"])
        result = await service.update_note(note_id, NoteUpdate(**update_fields))
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Note {note_id} not found")
        return result.model_dump()

    if command == "delete":
        note_id = int(arguments["id"])
        await service.delete_note(note_id)
        return {"deleted": True, "id": note_id}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown note command: {command}")
