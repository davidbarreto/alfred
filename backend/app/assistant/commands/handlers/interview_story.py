import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.assistant.commands.handlers._utils import optional_int, parse_tags, require_int
from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryRead
from app.features.organizer.interviews.stories.service import InterviewStoryService, StoryAssessmentError

logger = logging.getLogger(__name__)

_STAR_USAGE = "Use: situation | task | action | result"


def _summary(story: InterviewStoryRead, width: int = 80) -> dict[str, Any]:
    return {
        "id": story.id,
        "situation": story.situation[:width],
        "task": story.task[:width],
        "action": story.action[:width],
        "result": story.result[:width],
        "strength": story.strength,
        "tags": [t.tag for t in story.tags],
    }


def _parse_star(text: str | None) -> tuple[str, str, str, str]:
    parts = [p.strip() for p in (text or "").split("|")]
    if len(parts) != 4 or not all(parts):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_STAR_USAGE)
    return parts[0], parts[1], parts[2], parts[3]


async def handle_interview_story(command: str, arguments: dict[str, Any], service: InterviewStoryService) -> Any:
    logger.debug("handle_interview_story: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        situation, task, action, result = _parse_star(arguments.get("text"))
        try:
            data = InterviewStoryCreate(
                situation=situation,
                task=task,
                action=action,
                result=result,
                strength=optional_int(arguments, "strength", 3),
                tags=parse_tags(arguments.get("tags")),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.errors()[0]["msg"])
        story = await service.create_story(data)
        return {**_summary(story, width=100), "message": f"Story {story.id} created"}

    if command == "list":
        limit = optional_int(arguments, "limit", 20)
        offset = optional_int(arguments, "offset", 0)
        stories = await service.get_stories(tag=arguments.get("tag"), limit=limit + 1, offset=offset)
        return {
            "count": min(len(stories), limit),
            "has_next": len(stories) > limit,
            "stories": [_summary(s) for s in stories[:limit]],
        }

    if command == "search":
        query = (arguments.get("query") or "").strip()
        if not query:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="query is required")
        stories = await service.search_stories(query)
        return {"count": len(stories), "stories": [_summary(s) for s in stories]}

    if command == "tag":
        story_id = require_int(arguments, "id")
        tag = (arguments.get("tag") or "").strip()
        if not tag:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tag is required")
        story = await service.add_tag(story_id, tag)
        if story is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Story {story_id} not found")
        return {"id": story_id, "tags": [t.tag for t in story.tags], "message": f"Tag '{tag}' added to story {story_id}"}

    if command == "assess":
        story_id = require_int(arguments, "id")
        try:
            assessment = await service.assess_strength(story_id)
        except StoryAssessmentError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        if assessment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Story {story_id} not found")
        return assessment.model_dump()

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
