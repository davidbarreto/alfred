from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/interview-prep")

_STORIES_PAGE_SIZE = 20
_QUESTIONS_PAGE_SIZE = 15


def _pagination(items: list, page_size: int, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > page_size
    return items[:page_size], has_next, offset > 0


@router.get("/stories", response_class=HTMLResponse)
async def stories_list(request: Request, tag: str | None = None, offset: int = 0):
    try:
        params = {"limit": _STORIES_PAGE_SIZE + 1, "offset": offset}
        if tag:
            params["tag"] = tag
        stories = await api.get("/organizer/interview-stories", params=params)
        all_tags = await api.get("/organizer/interview-stories/tags")

        paginated_stories, has_next, has_prev = _pagination(stories, _STORIES_PAGE_SIZE, offset)

        return templates.TemplateResponse("interview_prep/stories.html", {
            "request": request,
            "stories": paginated_stories,
            "all_tags": all_tags,
            "current_tag": tag,
            "offset": offset,
            "has_next": has_next,
            "has_prev": has_prev,
            "next_offset": offset + _STORIES_PAGE_SIZE,
            "prev_offset": max(0, offset - _STORIES_PAGE_SIZE),
        })
    except httpx.HTTPError:
        return templates.TemplateResponse("interview_prep/stories.html", {
            "request": request, "stories": [], "all_tags": [], "error": "Failed to load stories"
        })


@router.post("/stories")
async def create_story(
    request: Request,
    situation: Annotated[str, Form()],
    task: Annotated[str, Form()],
    action: Annotated[str, Form()],
    result: Annotated[str, Form()],
    strength: Annotated[int, Form()] = 3,
):
    try:
        payload = {
            "situation": situation,
            "task": task,
            "action": action,
            "result": result,
            "strength": strength,
            "tags": [],
        }
        await api.post("/organizer/interview-stories", json=payload)
        return RedirectResponse(url="/interview-prep/stories", status_code=303)
    except httpx.HTTPError:
        return RedirectResponse(url="/interview-prep/stories", status_code=303)


@router.post("/stories/{story_id}/delete")
async def delete_story(story_id: int):
    try:
        await api.delete(f"/organizer/interview-stories/{story_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interview-prep/stories", status_code=303)


@router.post("/stories/{story_id}/tags")
async def add_tag(story_id: int, tag: Annotated[str, Form()]):
    try:
        await api.post(f"/organizer/interview-stories/{story_id}/tags/{tag}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interview-prep/stories", status_code=303)


@router.get("/prep-questions", response_class=HTMLResponse)
async def prep_questions_list(request: Request, offset: int = 0):
    try:
        questions = await api.get(
            "/organizer/interview-prep-questions",
            params={"limit": _QUESTIONS_PAGE_SIZE + 1, "offset": offset}
        )
        paginated_questions, has_next, has_prev = _pagination(questions, _QUESTIONS_PAGE_SIZE, offset)

        return templates.TemplateResponse("interview_prep/prep_questions.html", {
            "request": request,
            "questions": paginated_questions,
            "offset": offset,
            "has_next": has_next,
            "has_prev": has_prev,
            "next_offset": offset + _QUESTIONS_PAGE_SIZE,
            "prev_offset": max(0, offset - _QUESTIONS_PAGE_SIZE),
        })
    except httpx.HTTPError:
        return templates.TemplateResponse("interview_prep/prep_questions.html", {
            "request": request, "questions": [], "error": "Failed to load questions"
        })


@router.post("/prep-questions")
async def create_prep_question(request: Request, text: Annotated[str, Form()]):
    try:
        await api.post("/organizer/interview-prep-questions", json={"text": text})
        return RedirectResponse(url="/interview-prep/prep-questions", status_code=303)
    except httpx.HTTPError:
        return RedirectResponse(url="/interview-prep/prep-questions", status_code=303)


@router.get("/candidate-questions", response_class=HTMLResponse)
async def candidate_questions_list(request: Request, category: str | None = None, offset: int = 0):
    try:
        params = {"limit": 100, "offset": offset}
        if category:
            params["category"] = category
        questions = await api.get("/organizer/candidate-questions", params=params)
        all_categories = await api.get("/organizer/candidate-questions/categories")

        return templates.TemplateResponse("interview_prep/candidate_questions.html", {
            "request": request,
            "questions": questions,
            "all_categories": all_categories,
            "current_category": category,
        })
    except httpx.HTTPError:
        return templates.TemplateResponse("interview_prep/candidate_questions.html", {
            "request": request, "questions": [], "all_categories": [], "error": "Failed to load questions"
        })


@router.post("/candidate-questions")
async def create_candidate_question(
    request: Request,
    text: Annotated[str, Form()],
    category: Annotated[str, Form()],
):
    try:
        await api.post("/organizer/candidate-questions", json={"text": text, "category": category})
        return RedirectResponse(url="/interview-prep/candidate-questions", status_code=303)
    except httpx.HTTPError:
        return RedirectResponse(url="/interview-prep/candidate-questions", status_code=303)
