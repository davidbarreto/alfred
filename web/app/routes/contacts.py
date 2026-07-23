from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/contacts")

_PAGE_SIZE = 50


def _build_params(
    name: str,
    email: str,
    has_birthday: str,
    letter: str,
    offset: int,
    relationship: str = "",
) -> dict:
    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    if name:
        params["name"] = name
    if email:
        params["email"] = email
    if has_birthday in ("true", "false"):
        params["has_birthday"] = has_birthday
    if letter and len(letter) == 1:
        params["letter"] = letter
    if relationship:
        params["relationship"] = relationship
    return params


def _pagination(contacts: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(contacts) > _PAGE_SIZE
    return contacts[:_PAGE_SIZE], has_next, offset > 0


@router.get("/", response_class=HTMLResponse)
async def contacts_page(request: Request):
    name = request.query_params.get("name", "").strip()
    email = request.query_params.get("email", "").strip()
    has_birthday = request.query_params.get("has_birthday", "")
    letter = request.query_params.get("letter", "").strip().upper()
    relationship = request.query_params.get("relationship", "").strip()
    offset = max(0, int(request.query_params.get("offset", "0")))

    api_error: str | None = None
    try:
        raw = await api.get("/organizer/contacts", params=_build_params(name, email, has_birthday, letter, offset, relationship))
    except httpx.HTTPStatusError as e:
        raw = []
        api_error = f"API error {e.response.status_code}"
    except httpx.HTTPError:
        raw = []
        api_error = "Cannot reach backend"

    contacts, has_next, has_prev = _pagination(raw, offset)

    return templates.TemplateResponse(request, "contacts.html", {
        "contacts": contacts,
        "has_next": has_next,
        "has_prev": has_prev,
        "query_name": name,
        "query_email": email,
        "query_has_birthday": has_birthday,
        "query_letter": letter,
        "query_relationship": relationship,
        "query_offset": offset,
        "page_size": _PAGE_SIZE,
        "api_error": api_error,
    })


@router.get("/table", response_class=HTMLResponse)
async def contacts_table_fragment(request: Request):
    name = request.query_params.get("name", "").strip()
    email = request.query_params.get("email", "").strip()
    has_birthday = request.query_params.get("has_birthday", "")
    letter = request.query_params.get("letter", "").strip().upper()
    relationship = request.query_params.get("relationship", "").strip()
    offset = max(0, int(request.query_params.get("offset", "0")))

    try:
        raw = await api.get("/organizer/contacts", params=_build_params(name, email, has_birthday, letter, offset, relationship))
    except httpx.HTTPError:
        raw = []

    contacts, has_next, has_prev = _pagination(raw, offset)

    return templates.TemplateResponse(request, "_contacts_table.html", {
        "contacts": contacts,
        "has_next": has_next,
        "has_prev": has_prev,
    })


@router.post("/", response_class=HTMLResponse)
async def create_contact(
    request: Request,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    birthday: Annotated[str, Form()] = "",
):
    payload: dict = {"name": name}
    if email:
        payload["email"] = email
    if phone:
        payload["phone"] = phone
    if birthday:
        payload["birthday"] = birthday

    try:
        await api.post("/organizer/contacts", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create contact.</p>', status_code=422)

    try:
        raw = await api.get("/organizer/contacts", params={"limit": _PAGE_SIZE + 1, "offset": 0})
    except httpx.HTTPError:
        raw = []

    contacts, has_next, has_prev = _pagination(raw, 0)
    return templates.TemplateResponse(request, "_contacts_table.html", {
        "contacts": contacts,
        "has_next": has_next,
        "has_prev": has_prev,
    })


@router.patch("/{contact_id}/self", response_class=HTMLResponse)
async def set_contact_self(contact_id: int, request: Request, value: bool = True):
    offset = max(0, int(request.query_params.get("offset", "0")))
    letter = request.query_params.get("letter", "").strip().upper()
    has_birthday = request.query_params.get("has_birthday", "")

    try:
        await api.patch(f"/organizer/contacts/{contact_id}", json={"is_self": value})
    except httpx.HTTPError:
        pass

    try:
        raw = await api.get("/organizer/contacts", params=_build_params("", "", has_birthday, letter, offset))
    except httpx.HTTPError:
        raw = []

    contacts, has_next, has_prev = _pagination(raw, offset)
    return templates.TemplateResponse(request, "_contacts_table.html", {
        "contacts": contacts,
        "has_next": has_next,
        "has_prev": has_prev,
    })


@router.delete("/{contact_id}", response_class=HTMLResponse)
async def delete_contact(contact_id: int, request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    letter = request.query_params.get("letter", "").strip().upper()
    has_birthday = request.query_params.get("has_birthday", "")

    try:
        await api.delete(f"/organizer/contacts/{contact_id}")
    except httpx.HTTPError:
        pass

    try:
        raw = await api.get("/organizer/contacts", params=_build_params("", "", has_birthday, letter, offset))
    except httpx.HTTPError:
        raw = []

    contacts, has_next, has_prev = _pagination(raw, offset)
    return templates.TemplateResponse(request, "_contacts_table.html", {
        "contacts": contacts,
        "has_next": has_next,
        "has_prev": has_prev,
    })
