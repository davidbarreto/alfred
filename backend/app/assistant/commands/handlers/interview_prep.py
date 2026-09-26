import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.interviews.prep_questions.schemas import InterviewPrepQuestionCreate, InterviewPrepQuestionUpdate
from app.features.organizer.interviews.prep_questions.service import InterviewPrepQuestionService

logger = logging.getLogger(__name__)


async def handle_interview_prep(command: str, arguments: dict[str, Any], service: InterviewPrepQuestionService) -> Any:
    logger.debug("handle_interview_prep: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        text = arguments.get("text")
        if not text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text required")

        data = InterviewPrepQuestionCreate(text=text)
        question = await service.create_question(data)
        return {
            "id": question.id,
            "text": question.text,
            "message": f"Prep question {question.id} created",
        }

    if command == "list":
        limit = int(arguments.get("limit", 20))
        offset = int(arguments.get("offset", 0))
        questions = await service.get_questions(limit=limit + 1, offset=offset)

        has_next = len(questions) > limit
        questions = questions[:limit]

        return {
            "count": len(questions),
            "has_next": has_next,
            "questions": [
                {"id": q.id, "text": q.text}
                for q in questions
            ],
        }

    if command == "get":
        question_id = int(arguments.get("id"))
        question = await service.get_question_with_stories(question_id)
        if not question:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Question {question_id} not found")

        # Format with linked stories
        return {
            "id": question.id,
            "text": question.text,
            "stories": [
                {
                    "id": s.id,
                    "situation": s.situation[:60],
                    "strength": s.strength,
                }
                for s in question.stories
            ],
        }

    if command == "link":
        question_id = int(arguments.get("question_id"))
        story_id = int(arguments.get("story_id"))
        fit_score = int(arguments.get("fit_score", 3))

        if fit_score < 1 or fit_score > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fit_score must be 1-5")

        success = await service.link_story(question_id, story_id, fit_score)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        return {"message": f"Story {story_id} linked to question {question_id} with fit={fit_score}"}

    if command == "unlink":
        question_id = int(arguments.get("question_id"))
        story_id = int(arguments.get("story_id"))

        success = await service.unlink_story(question_id, story_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
        return {"message": f"Story {story_id} unlinked from question {question_id}"}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
