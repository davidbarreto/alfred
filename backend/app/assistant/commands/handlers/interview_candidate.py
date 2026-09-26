import logging
from typing import Any

from fastapi import HTTPException, status

from app.features.organizer.interviews.interviewee_questions.schemas import InterviewCandidateQuestionCreate, InterviewCandidateQuestionUpdate
from app.features.organizer.interviews.interviewee_questions.service import InterviewCandidateQuestionService

logger = logging.getLogger(__name__)


async def handle_interview_candidate(
    command: str, arguments: dict[str, Any], service: InterviewCandidateQuestionService
) -> Any:
    logger.debug("handle_interview_candidate: command=%s args_keys=%s", command, list(arguments.keys()))

    if command == "add":
        text = arguments.get("text")
        category = arguments.get("category")
        if not text or not category:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text and category required")

        data = InterviewCandidateQuestionCreate(text=text, category=category)
        question = await service.create_question(data)
        return {
            "id": question.id,
            "text": question.text,
            "category": question.category,
            "message": f"Candidate question {question.id} created",
        }

    if command == "list":
        category = arguments.get("category")
        limit = int(arguments.get("limit", 50))
        offset = int(arguments.get("offset", 0))

        if category:
            questions = await service.get_questions_by_category(category, limit=limit + 1, offset=offset)
        else:
            questions = await service.get_questions(limit=limit + 1, offset=offset)

        has_next = len(questions) > limit
        questions = questions[:limit]

        return {
            "count": len(questions),
            "has_next": has_next,
            "questions": [
                {"id": q.id, "text": q.text, "category": q.category}
                for q in questions
            ],
        }

    if command == "categories":
        categories = await service.get_all_categories()
        return {"categories": categories, "count": len(categories)}

    if command == "get":
        question_id = int(arguments.get("id"))
        question = await service.get_question(question_id)
        if not question:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Question {question_id} not found")
        return {"id": question.id, "text": question.text, "category": question.category}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown command: {command}")
