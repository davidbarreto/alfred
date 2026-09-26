import logging
from typing import Annotated
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import app.client as api
from app.templates_config import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview-prep")

_STORIES_PAGE_SIZE = 20
_QUESTIONS_PAGE_SIZE = 15
_CANDIDATE_CATEGORIES = ["Onboarding", "Tech", "Culture", "Benefits", "Logistics", "Growth", "Work-life"]


def _pagination(items: list, page_size: int, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > page_size
    return items[:page_size], has_next, offset > 0


def _redirect(url: str, error: str | None = None) -> RedirectResponse:
    if error:
        url = f"{url}?{urlencode({'error': error})}"
    return RedirectResponse(url=url, status_code=303)


def _api_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except ValueError:
            detail = None
        if isinstance(detail, str):
            return detail
        return f"Backend returned {exc.response.status_code}"
    return "Backend unreachable"


@router.get("/stories", response_class=HTMLResponse)
async def stories_list(request: Request, tag: str | None = None, offset: int = 0, error: str | None = None):
    context = {"current_tag": tag, "stories": [], "all_tags": [], "error": error}
    try:
        params: dict = {"limit": _STORIES_PAGE_SIZE + 1, "offset": offset}
        if tag:
            params["tag"] = tag
        stories = await api.get("/organizer/interview-stories", params=params)
        context["all_tags"] = await api.get("/organizer/interview-stories/tags")
        stories, has_next, has_prev = _pagination(stories, _STORIES_PAGE_SIZE, offset)
        context.update(
            stories=stories,
            has_next=has_next,
            has_prev=has_prev,
            next_offset=offset + _STORIES_PAGE_SIZE,
            prev_offset=max(0, offset - _STORIES_PAGE_SIZE),
        )
    except httpx.HTTPError as exc:
        context["error"] = _api_error(exc)
    return templates.TemplateResponse(request, "interview_prep/stories.html", context)


@router.post("/stories")
async def create_story(
    situation: Annotated[str, Form()],
    task: Annotated[str, Form()],
    action: Annotated[str, Form()],
    result: Annotated[str, Form()],
    strength: Annotated[int, Form()] = 3,
    tags: Annotated[str, Form()] = "",
):
    payload = {
        "situation": situation,
        "task": task,
        "action": action,
        "result": result,
        "strength": strength,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    }
    try:
        await api.post("/organizer/interview-stories", json=payload)
    except httpx.HTTPError as exc:
        logger.warning("Create interview story failed: %s", exc)
        return _redirect("/interview-prep/stories", _api_error(exc))
    return _redirect("/interview-prep/stories")


@router.post("/stories/{story_id}/delete")
async def delete_story(story_id: int):
    try:
        await api.delete(f"/organizer/interview-stories/{story_id}")
    except httpx.HTTPError as exc:
        return _redirect("/interview-prep/stories", _api_error(exc))
    return _redirect("/interview-prep/stories")


@router.post("/stories/{story_id}/tags")
async def add_tag(story_id: int, tag: Annotated[str, Form()]):
    try:
        await api.post(f"/organizer/interview-stories/{story_id}/tags/{quote(tag.strip(), safe='')}")
    except httpx.HTTPError as exc:
        return _redirect("/interview-prep/stories", _api_error(exc))
    return _redirect("/interview-prep/stories")


@router.get("/prep-questions", response_class=HTMLResponse)
async def prep_questions_list(request: Request, offset: int = 0, error: str | None = None):
    context = {"questions": [], "error": error}
    try:
        questions = await api.get(
            "/organizer/interview-prep-questions", params={"limit": _QUESTIONS_PAGE_SIZE + 1, "offset": offset}
        )
        questions, has_next, has_prev = _pagination(questions, _QUESTIONS_PAGE_SIZE, offset)
        context.update(
            questions=questions,
            has_next=has_next,
            has_prev=has_prev,
            next_offset=offset + _QUESTIONS_PAGE_SIZE,
            prev_offset=max(0, offset - _QUESTIONS_PAGE_SIZE),
        )
    except httpx.HTTPError as exc:
        context["error"] = _api_error(exc)
    return templates.TemplateResponse(request, "interview_prep/prep_questions.html", context)


@router.post("/prep-questions")
async def create_prep_question(text: Annotated[str, Form()]):
    try:
        await api.post("/organizer/interview-prep-questions", json={"text": text})
    except httpx.HTTPError as exc:
        return _redirect("/interview-prep/prep-questions", _api_error(exc))
    return _redirect("/interview-prep/prep-questions")


@router.get("/prep-questions/{question_id}", response_class=HTMLResponse)
async def prep_question_detail(request: Request, question_id: int, error: str | None = None):
    context = {"question": None, "linkable_stories": [], "error": error}
    try:
        question = await api.get(f"/organizer/interview-prep-questions/{question_id}")
        all_stories = await api.get("/organizer/interview-stories", params={"limit": 500})
        linked_ids = {s["id"] for s in question["stories"]}
        context.update(
            question=question,
            linkable_stories=[s for s in all_stories if s["id"] not in linked_ids],
        )
    except httpx.HTTPError as exc:
        context["error"] = _api_error(exc)
    return templates.TemplateResponse(request, "interview_prep/prep_question_detail.html", context)


@router.post("/prep-questions/{question_id}/link")
async def link_story(
    question_id: int,
    story_id: Annotated[int, Form()],
    fit_score: Annotated[int, Form()] = 3,
):
    url = f"/interview-prep/prep-questions/{question_id}"
    try:
        await api.put(
            f"/organizer/interview-prep-questions/{question_id}/stories/{story_id}", json={"fit_score": fit_score}
        )
    except httpx.HTTPError as exc:
        return _redirect(url, _api_error(exc))
    return _redirect(url)


@router.post("/prep-questions/{question_id}/stories/{story_id}/unlink")
async def unlink_story(question_id: int, story_id: int):
    url = f"/interview-prep/prep-questions/{question_id}"
    try:
        await api.delete(f"/organizer/interview-prep-questions/{question_id}/stories/{story_id}")
    except httpx.HTTPError as exc:
        return _redirect(url, _api_error(exc))
    return _redirect(url)


@router.get("/candidate-questions", response_class=HTMLResponse)
async def candidate_questions_list(request: Request, category: str | None = None, error: str | None = None):
    context = {
        "questions": [],
        "all_categories": [],
        "category_options": _CANDIDATE_CATEGORIES,
        "current_category": category,
        "error": error,
    }
    try:
        params: dict = {"limit": 500}
        if category:
            params["category"] = category
        context["questions"] = await api.get("/organizer/candidate-questions", params=params)
        context["all_categories"] = await api.get("/organizer/candidate-questions/categories")
    except httpx.HTTPError as exc:
        context["error"] = _api_error(exc)
    return templates.TemplateResponse(request, "interview_prep/candidate_questions.html", context)


@router.post("/candidate-questions")
async def create_candidate_question(text: Annotated[str, Form()], category: Annotated[str, Form()]):
    try:
        await api.post("/organizer/candidate-questions", json={"text": text, "category": category})
    except httpx.HTTPError as exc:
        return _redirect("/interview-prep/candidate-questions", _api_error(exc))
    return _redirect("/interview-prep/candidate-questions")
