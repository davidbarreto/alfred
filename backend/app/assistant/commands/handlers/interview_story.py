import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.interviews.stories.schemas import InterviewStoryCreate, InterviewStoryUpdate
from app.features.organizer.interviews.stories.service import InterviewStoryService
from app.shared.llm import LlmProvider

logger = logging.getLogger(__name__)


async def handle_interview_story(
    command: str,
    arguments: dict[str, Any],
    service: InterviewStoryService,
    llm_provider: LlmProvider | None = None,
) -> Any:
    logger.debug("handle_interview_story: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        data = InterviewStoryCreate(
            situation=arguments.get("situation", ""),
            task=arguments.get("task", ""),
            action=arguments.get("action", ""),
            result=arguments.get("result", ""),
            strength=int(arguments.get("strength", 3)),
            tags=arguments.get("tags", "").split(",") if arguments.get("tags") else [],
        )
        story = await service.create_story(data)
        return {
            "id": story.id,
            "situation": story.situation[:100],
            "task": story.task[:100],
            "action": story.action[:100],
            "result": story.result[:100],
            "strength": story.strength,
            "tags": [t.tag for t in story.tags],
            "message": f"Story {story.id} created",
        }

    if command == "list":
        tag = arguments.get("tag")
        limit = int(arguments.get("limit", 20))
        offset = int(arguments.get("offset", 0))

        if tag:
            stories = await service.get_stories_by_tag(tag, limit=limit + 1, offset=offset)
        else:
            stories = await service.get_stories(limit=limit + 1, offset=offset)

        has_next = len(stories) > limit
        stories = stories[:limit]

        return {
            "count": len(stories),
            "has_next": has_next,
            "stories": [
                {
                    "id": s.id,
                    "situation": s.situation[:80],
                    "task": s.task[:80],
                    "action": s.action[:80],
                    "result": s.result[:80],
                    "strength": s.strength,
                    "tags": [t.tag for t in s.tags],
                }
                for s in stories
            ],
        }

    if command == "search":
        query = arguments.get("query", "").lower()
        if not query:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="query required")

        stories = await service.get_stories(limit=100)
        matched = [
            {
                "id": s.id,
                "situation": s.situation[:80],
                "task": s.task[:80],
                "action": s.action[:80],
                "result": s.result[:80],
                "strength": s.strength,
                "tags": [t.tag for t in s.tags],
            }
            for s in stories
            if query in s.situation.lower()
            or query in s.task.lower()
            or query in s.action.lower()
            or query in s.result.lower()
            or any(query in t.tag.lower() for t in s.tags)
        ]
        return {"count": len(matched), "stories": matched}

    if command == "tag":
        story_id = int(arguments.get("id"))
        tag = arguments.get("tag")
        if not tag:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tag required")

        success = await service.add_tag(story_id, tag)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Story {story_id} not found")
        return {"message": f"Tag '{tag}' added to story {story_id}"}

    if command == "assess":
        story_id = int(arguments.get("id"))
        if not llm_provider:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLM provider not available",
            )

        score = await service.assess_strength(story_id)
        if score is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to assess")
        return {"story_id": story_id, "suggested_strength": score}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
