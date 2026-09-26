import logging
from typing import Any

from fastapi import HTTPException, status

from app.assistant.commands.handlers._utils import optional_int, require_int
from app.features.organizer.interviews.prep_questions.schemas import InterviewPrepQuestionCreate
from app.features.organizer.interviews.prep_questions.service import InterviewPrepQuestionService

logger = logging.getLogger(__name__)


async def handle_interview_prep(command: str, arguments: dict[str, Any], service: InterviewPrepQuestionService) -> Any:
    logger.debug("handle_interview_prep: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        text = (arguments.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text is required")
        question = await service.create_question(InterviewPrepQuestionCreate(text=text))
        return {"id": question.id, "text": question.text, "message": f"Prep question {question.id} created"}

    if command == "list":
        limit = optional_int(arguments, "limit", 20)
        offset = optional_int(arguments, "offset", 0)
        questions = await service.get_questions(limit=limit + 1, offset=offset)
        return {
            "count": min(len(questions), limit),
            "has_next": len(questions) > limit,
            "questions": [{"id": q.id, "text": q.text} for q in questions[:limit]],
        }

    if command == "get":
        question_id = require_int(arguments, "id")
        question = await service.get_question_with_stories(question_id)
        if question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Question {question_id} not found")
        return {
            "id": question.id,
            "text": question.text,
            "stories": [
                {"id": s.id, "situation": s.situation[:60], "strength": s.strength, "fit_score": s.fit_score}
                for s in question.stories
            ],
        }

    if command == "link":
        question_id = require_int(arguments, "question_id")
        story_id = require_int(arguments, "story_id")
        fit_score = optional_int(arguments, "fit_score", 3)
        if not 1 <= fit_score <= 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fit_score must be 1-5")
        link = await service.link_story(question_id, story_id, fit_score)
        if link is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question or story not found")
        return {**link.model_dump(), "message": f"Story {story_id} linked to question {question_id} with fit={fit_score}"}

    if command == "unlink":
        question_id = require_int(arguments, "question_id")
        story_id = require_int(arguments, "story_id")
        if not await service.unlink_story(question_id, story_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        return {"message": f"Story {story_id} unlinked from question {question_id}"}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
