from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/contacts")


@router.get("/", response_class=HTMLResponse)
async def contacts_page(request: Request):
    name = request.query_params.get("name", "").strip()
    email = request.query_params.get("email", "").strip()
    has_birthday = request.query_params.get("has_birthday", "")

    params: dict = {"limit": 200}
    if name:
        params["name"] = name
    if email:
        params["email"] = email
    if has_birthday in ("true", "false"):
        params["has_birthday"] = has_birthday

    api_error: str | None = None
    try:
        contacts = await api.get("/organizer/contacts/", params=params)
    except httpx.HTTPStatusError as e:
        contacts = []
        api_error = f"API error {e.response.status_code}"
    except httpx.HTTPError:
        contacts = []
        api_error = "Cannot reach backend"

    return templates.TemplateResponse(request, "contacts.html", {
        "contacts": contacts,
        "query_name": name,
        "query_email": email,
        "query_has_birthday": has_birthday,
        "api_error": api_error,
    })


@router.get("/table", response_class=HTMLResponse)
async def contacts_table_fragment(request: Request):
    name = request.query_params.get("name", "").strip()
    email = request.query_params.get("email", "").strip()
    has_birthday = request.query_params.get("has_birthday", "")

    params: dict = {"limit": 200}
    if name:
        params["name"] = name
    if email:
        params["email"] = email
    if has_birthday in ("true", "false"):
        params["has_birthday"] = has_birthday

    try:
        contacts = await api.get("/organizer/contacts/", params=params)
    except httpx.HTTPError:
        contacts = []

    return templates.TemplateResponse(request, "_contacts_table.html", {"contacts": contacts})


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
        await api.post("/organizer/contacts/", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create contact.</p>', status_code=422)

    try:
        contacts = await api.get("/organizer/contacts/", params={"limit": 200})
    except httpx.HTTPError:
        contacts = []

    return templates.TemplateResponse(request, "_contacts_table.html", {"contacts": contacts})


@router.delete("/{contact_id}", response_class=HTMLResponse)
async def delete_contact(contact_id: int, request: Request):
    try:
        await api.delete(f"/organizer/contacts/{contact_id}")
    except httpx.HTTPError:
        pass

    try:
        contacts = await api.get("/organizer/contacts/", params={"limit": 200})
    except httpx.HTTPError:
        contacts = []

    return templates.TemplateResponse(request, "_contacts_table.html", {"contacts": contacts})
