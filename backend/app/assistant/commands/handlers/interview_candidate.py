import logging
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from app.assistant.commands.handlers._utils import optional_int, require_int
from app.features.organizer.interviews.candidate_questions.schemas import InterviewCandidateQuestionCreate
from app.features.organizer.interviews.candidate_questions.service import InterviewCandidateQuestionService

logger = logging.getLogger(__name__)


async def handle_interview_candidate(
    command: str, arguments: dict[str, Any], service: InterviewCandidateQuestionService
) -> Any:
    logger.debug("handle_interview_candidate: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        text = (arguments.get("text") or "").strip()
        category = (arguments.get("category") or "").strip()
        if not text or not category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="text and --category are required"
            )
        try:
            data = InterviewCandidateQuestionCreate(text=text, category=category)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.errors()[0]["msg"])
        question = await service.create_question(data)
        return {
            "id": question.id,
            "text": question.text,
            "category": question.category,
            "message": f"Candidate question {question.id} created",
        }

    if command == "list":
        limit = optional_int(arguments, "limit", 50)
        offset = optional_int(arguments, "offset", 0)
        questions = await service.get_questions(category=arguments.get("category"), limit=limit + 1, offset=offset)
        return {
            "count": min(len(questions), limit),
            "has_next": len(questions) > limit,
            "questions": [{"id": q.id, "text": q.text, "category": q.category} for q in questions[:limit]],
        }

    if command == "categories":
        categories = await service.get_all_categories()
        return {"categories": categories, "count": len(categories)}

    if command == "get":
        question_id = require_int(arguments, "id")
        question = await service.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Question {question_id} not found")
        return {"id": question.id, "text": question.text, "category": question.category}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
