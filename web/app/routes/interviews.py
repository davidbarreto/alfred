from typing import Annotated

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import app.client as api
from app.templates_config import templates

router = APIRouter(prefix="/interviews")

_PAGE_SIZE = 20


def _pagination(items: list, offset: int) -> tuple[list, bool, bool]:
    has_next = len(items) > _PAGE_SIZE
    return items[:_PAGE_SIZE], has_next, offset > 0


async def _get_companies() -> list:
    try:
        return await api.get("/organizer/interview-companies", params={"limit": 1000})
    except httpx.HTTPError:
        return []


# -- Companies -----------------------------------------------------------
# Registered before "/{process_id}" so "/companies..." isn't swallowed by
# the process-detail route's int path-param match failing into a 422.


@router.get("/companies", response_class=HTMLResponse)
async def companies_page(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    try:
        raw = await api.get("/organizer/interview-companies", params={"limit": _PAGE_SIZE + 1, "offset": offset})
    except httpx.HTTPError:
        raw = []
    companies, has_next, has_prev = _pagination(raw, offset)
    return templates.TemplateResponse(request, "interview_companies.html", {
        "companies": companies,
        "has_next": has_next,
        "has_prev": has_prev,
        "query_offset": offset,
    })


@router.get("/companies/table", response_class=HTMLResponse)
async def companies_table_fragment(request: Request):
    offset = max(0, int(request.query_params.get("offset", "0")))
    try:
        raw = await api.get("/organizer/interview-companies", params={"limit": _PAGE_SIZE + 1, "offset": offset})
    except httpx.HTTPError:
        raw = []
    companies, has_next, has_prev = _pagination(raw, offset)
    return templates.TemplateResponse(request, "_interview_companies_table.html", {
        "companies": companies,
        "has_next": has_next,
        "has_prev": has_prev,
        "query_offset": offset,
    })


@router.post("/companies")
async def create_company(name: Annotated[str, Form()], website: Annotated[str, Form()] = ""):
    payload: dict = {"name": name}
    if website:
        payload["website"] = website
    try:
        await api.post("/organizer/interview-companies", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interviews/companies", status_code=303)


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_detail(request: Request, company_id: int):
    try:
        company = await api.get(f"/organizer/interview-companies/{company_id}")
    except httpx.HTTPError:
        return RedirectResponse(url="/interviews/companies", status_code=303)
    try:
        processes = await api.get("/organizer/interview-processes", params={"company_id": company_id, "limit": 200})
    except httpx.HTTPError:
        processes = []
    return templates.TemplateResponse(request, "interview_company_detail.html", {
        "company": company,
        "processes": processes,
    })


@router.post("/companies/{company_id}/update")
async def update_company(
    company_id: int,
    name: Annotated[str, Form()] = "",
    website: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    payload: dict = {}
    if name:
        payload["name"] = name
    payload["website"] = website or None
    payload["notes"] = notes or None
    try:
        await api.patch(f"/organizer/interview-companies/{company_id}", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/companies/{company_id}", status_code=303)


@router.post("/companies/{company_id}/delete")
async def delete_company(company_id: int):
    try:
        await api.delete(f"/organizer/interview-companies/{company_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interviews/companies", status_code=303)


# -- Process list ----------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def interviews_page(request: Request):
    status_filter = request.query_params.get("status", "").strip()
    offset = max(0, int(request.query_params.get("offset", "0")))

    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    if status_filter:
        params["status"] = status_filter

    api_error: str | None = None
    try:
        raw = await api.get("/organizer/interview-processes", params=params)
    except httpx.HTTPError:
        raw = []
        api_error = "Cannot reach backend"

    processes, has_next, has_prev = _pagination(raw, offset)
    companies = await _get_companies()

    try:
        insights = await api.get("/organizer/interview-insights", params={"limit": 5})
    except httpx.HTTPError:
        insights = []

    return templates.TemplateResponse(request, "interviews.html", {
        "processes": processes,
        "companies": companies,
        "insights": insights,
        "has_next": has_next,
        "has_prev": has_prev,
        "query_status": status_filter,
        "query_offset": offset,
        "api_error": api_error,
    })


@router.get("/table", response_class=HTMLResponse)
async def interviews_table_fragment(request: Request):
    status_filter = request.query_params.get("status", "").strip()
    offset = max(0, int(request.query_params.get("offset", "0")))

    params: dict = {"limit": _PAGE_SIZE + 1, "offset": offset}
    if status_filter:
        params["status"] = status_filter

    try:
        raw = await api.get("/organizer/interview-processes", params=params)
    except httpx.HTTPError:
        raw = []

    processes, has_next, has_prev = _pagination(raw, offset)
    companies = await _get_companies()

    return templates.TemplateResponse(request, "_interviews_table.html", {
        "processes": processes,
        "companies": companies,
        "has_next": has_next,
        "has_prev": has_prev,
    })


@router.post("/extract", response_class=JSONResponse)
async def extract_from_url(url: Annotated[str, Form()]):
    try:
        result = await api.post("/organizer/interview-processes/extract-from-url", json={"url": url})
    except httpx.HTTPError:
        return JSONResponse({"error": "Extraction failed."}, status_code=422)
    return JSONResponse(result)


@router.post("/")
async def create_process(
    request: Request,
    company_id: Annotated[str, Form()] = "",
    new_company_name: Annotated[str, Form()] = "",
    role_title: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
    priority: Annotated[str, Form()] = "",
    work_regime: Annotated[str, Form()] = "",
    office_days_per_month: Annotated[str, Form()] = "",
    office_location: Annotated[str, Form()] = "",
    salary_min: Annotated[str, Form()] = "",
    salary_max: Annotated[str, Form()] = "",
    salary_currency: Annotated[str, Form()] = "",
    benefits: Annotated[str, Form()] = "",
    job_description_url: Annotated[str, Form()] = "",
    first_stage_type: Annotated[str, Form()] = "",
    first_stage_scheduled_at: Annotated[str, Form()] = "",
):
    resolved_company_id = company_id
    if not resolved_company_id and new_company_name:
        try:
            company = await api.post("/organizer/interview-companies", json={"name": new_company_name})
            resolved_company_id = company["id"]
        except httpx.HTTPError:
            return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create company.</p>', status_code=422)

    if not resolved_company_id or not role_title:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Company and role title are required.</p>', status_code=422)

    process_payload: dict = {"company_id": int(resolved_company_id), "role_title": role_title}
    if source:
        process_payload["source"] = source
    if priority:
        process_payload["priority"] = priority
    if work_regime:
        process_payload["work_regime"] = work_regime
    if office_days_per_month:
        process_payload["office_days_per_month"] = float(office_days_per_month)
    if office_location:
        process_payload["office_location"] = office_location
    if salary_min:
        process_payload["salary_min"] = int(salary_min)
    if salary_max:
        process_payload["salary_max"] = int(salary_max)
    if salary_currency:
        process_payload["salary_currency"] = salary_currency
    if benefits:
        process_payload["benefits"] = benefits
    if job_description_url:
        process_payload["job_description_url"] = job_description_url

    payload: dict = {"process": process_payload}
    if first_stage_type:
        first_stage: dict = {"stage_type": first_stage_type}
        if first_stage_scheduled_at:
            first_stage["scheduled_at"] = first_stage_scheduled_at
        payload["first_stage"] = first_stage

    try:
        await api.post("/organizer/interview-processes", json=payload)
    except httpx.HTTPError:
        return HTMLResponse('<p class="text-[#E24B4A] text-sm">Failed to create interview process.</p>', status_code=422)

    return RedirectResponse(url="/interviews", status_code=303)


@router.post("/{process_id}/delete")
async def delete_process(process_id: int):
    try:
        await api.delete(f"/organizer/interview-processes/{process_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interviews", status_code=303)


# -- Process edit ------------------------------------------------------------


@router.get("/{process_id}/edit", response_class=HTMLResponse)
async def edit_process_page(request: Request, process_id: int):
    try:
        process = await api.get(f"/organizer/interview-processes/{process_id}")
    except httpx.HTTPError:
        return RedirectResponse(url="/interviews", status_code=303)
    companies = await _get_companies()
    return templates.TemplateResponse(request, "interview_process_edit.html", {
        "process": process,
        "companies": companies,
    })


@router.post("/{process_id}/update")
async def update_process(
    process_id: int,
    company_id: Annotated[str, Form()] = "",
    role_title: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "",
    priority: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
    applied_date: Annotated[str, Form()] = "",
    work_regime: Annotated[str, Form()] = "",
    office_days_per_month: Annotated[str, Form()] = "",
    office_location: Annotated[str, Form()] = "",
    salary_min: Annotated[str, Form()] = "",
    salary_max: Annotated[str, Form()] = "",
    salary_currency: Annotated[str, Form()] = "",
    benefits: Annotated[str, Form()] = "",
    job_description_url: Annotated[str, Form()] = "",
):
    payload: dict = {}
    if company_id:
        payload["company_id"] = int(company_id)
    if role_title:
        payload["role_title"] = role_title
    if status:
        payload["status"] = status
    payload["priority"] = priority or None
    payload["source"] = source or None
    payload["applied_date"] = applied_date or None
    payload["work_regime"] = work_regime or None
    payload["office_days_per_month"] = float(office_days_per_month) if office_days_per_month else None
    payload["office_location"] = office_location or None
    payload["salary_min"] = int(salary_min) if salary_min else None
    payload["salary_max"] = int(salary_max) if salary_max else None
    payload["salary_currency"] = salary_currency or None
    payload["benefits"] = benefits or None
    payload["job_description_url"] = job_description_url or None
    try:
        await api.patch(f"/organizer/interview-processes/{process_id}", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


# -- Process detail ----------------------------------------------------------


async def _get_stage_links(stage_id: int) -> dict:
    contacts, tasks, notes = [], [], []
    try:
        contacts = await api.get(f"/organizer/interview-stages/{stage_id}/contacts")
    except httpx.HTTPError:
        pass
    try:
        tasks = await api.get(f"/organizer/interview-stages/{stage_id}/tasks")
    except httpx.HTTPError:
        pass
    try:
        notes = await api.get(f"/organizer/interview-stages/{stage_id}/notes")
    except httpx.HTTPError:
        pass
    return {"contacts": contacts, "tasks": tasks, "notes": notes}


async def _get_calendar_event(event_id: int | None):
    if not event_id:
        return None
    try:
        return await api.get(f"/organizer/calendar-events/{event_id}")
    except httpx.HTTPError:
        return None


@router.get("/{process_id}", response_class=HTMLResponse)
async def interview_process_detail(request: Request, process_id: int):
    try:
        process = await api.get(f"/organizer/interview-processes/{process_id}")
    except httpx.HTTPError:
        return RedirectResponse(url="/interviews", status_code=303)

    try:
        company = await api.get(f"/organizer/interview-companies/{process['company_id']}")
    except httpx.HTTPError:
        company = None

    try:
        links = await api.get("/organizer/interview-links", params={"process_id": process_id})
    except httpx.HTTPError:
        links = []

    stage_extras: dict[int, dict] = {}
    for s in process.get("stages", []):
        stage_extras[s["id"]] = await _get_stage_links(s["id"])
        stage_extras[s["id"]]["event"] = await _get_calendar_event(s.get("calendar_event_id"))

    return templates.TemplateResponse(request, "interview_process_detail.html", {
        "process": process,
        "company": company,
        "links": links,
        "stage_extras": stage_extras,
    })


@router.post("/{process_id}/stages")
async def create_stage(
    process_id: int,
    stage_type: Annotated[str, Form()],
    scheduled_at: Annotated[str, Form()] = "",
    sequence: Annotated[str, Form()] = "0",
):
    payload: dict = {"process_id": process_id, "stage_type": stage_type, "sequence": int(sequence or 0)}
    if scheduled_at:
        payload["scheduled_at"] = scheduled_at
    try:
        await api.post("/organizer/interview-stages", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/update")
async def update_stage(
    process_id: int,
    stage_id: int,
    stage_type: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "",
    scheduled_at: Annotated[str, Form()] = "",
    sequence: Annotated[str, Form()] = "",
    feedback: Annotated[str, Form()] = "",
    notes: Annotated[str, Form()] = "",
):
    payload: dict = {}
    if stage_type:
        payload["stage_type"] = stage_type
    if status:
        payload["status"] = status
    if scheduled_at:
        payload["scheduled_at"] = scheduled_at
    if sequence:
        payload["sequence"] = int(sequence)
    if feedback:
        payload["feedback"] = feedback
    if notes:
        payload["notes"] = notes
    try:
        await api.patch(f"/organizer/interview-stages/{stage_id}", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/delete")
async def delete_stage(process_id: int, stage_id: int):
    try:
        await api.delete(f"/organizer/interview-stages/{stage_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/feedback")
async def update_company_feedback(process_id: int, company_feedback: Annotated[str, Form()] = ""):
    try:
        await api.patch(f"/organizer/interview-processes/{process_id}", json={"company_feedback": company_feedback})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/links")
async def create_link(process_id: int, url: Annotated[str, Form()], label: Annotated[str, Form()] = ""):
    payload: dict = {"process_id": process_id, "url": url}
    if label:
        payload["label"] = label
    try:
        await api.post("/organizer/interview-links", json=payload)
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/links/{link_id}/delete")
async def delete_link(process_id: int, link_id: int):
    try:
        await api.delete(f"/organizer/interview-links/{link_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/insights/generate")
async def generate_insights():
    try:
        await api.post("/organizer/interview-insights")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url="/interviews", status_code=303)


# -- Stage <-> task/note/contact/calendar-event linking -----------------------


@router.get("/{process_id}/stages/{stage_id}/search/tasks", response_class=HTMLResponse)
async def search_tasks(request: Request, process_id: int, stage_id: int):
    query = request.query_params.get("q", "").strip()
    results = []
    if query:
        try:
            results = await api.get("/organizer/tasks", params={"q": query, "status": "ACTIVE", "limit": 8})
        except httpx.HTTPError:
            results = []
    return templates.TemplateResponse(request, "_interview_link_suggestions.html", {
        "results": results,
        "process_id": process_id,
        "stage_id": stage_id,
        "entity": "tasks",
        "label_field": "title",
    })


@router.get("/{process_id}/stages/{stage_id}/search/notes", response_class=HTMLResponse)
async def search_notes(request: Request, process_id: int, stage_id: int):
    query = request.query_params.get("q", "").strip()
    results = []
    if query:
        try:
            results = await api.get("/organizer/notes", params={"q": query, "limit": 8})
        except httpx.HTTPError:
            results = []
    return templates.TemplateResponse(request, "_interview_link_suggestions.html", {
        "results": results,
        "process_id": process_id,
        "stage_id": stage_id,
        "entity": "notes",
        "label_field": "title",
    })


@router.get("/{process_id}/stages/{stage_id}/search/contacts", response_class=HTMLResponse)
async def search_contacts(request: Request, process_id: int, stage_id: int):
    query = request.query_params.get("q", "").strip()
    results = []
    if query:
        try:
            results = await api.get("/organizer/contacts", params={"name": query, "limit": 8})
        except httpx.HTTPError:
            results = []
    return templates.TemplateResponse(request, "_interview_link_suggestions.html", {
        "results": results,
        "process_id": process_id,
        "stage_id": stage_id,
        "entity": "contacts",
        "label_field": "name",
    })


@router.get("/{process_id}/stages/{stage_id}/search/events", response_class=HTMLResponse)
async def search_events(request: Request, process_id: int, stage_id: int):
    query = request.query_params.get("q", "").strip()
    results = []
    if query:
        try:
            results = await api.get("/organizer/calendar-events", params={"q": query, "limit": 8})
        except httpx.HTTPError:
            results = []
    return templates.TemplateResponse(request, "_interview_link_suggestions.html", {
        "results": results,
        "process_id": process_id,
        "stage_id": stage_id,
        "entity": "events",
        "label_field": "title",
    })


@router.post("/{process_id}/stages/{stage_id}/tasks/{task_id}/link")
async def link_task(process_id: int, stage_id: int, task_id: int):
    try:
        await api.post(f"/organizer/interview-stages/{stage_id}/tasks/{task_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/tasks/{task_id}/unlink")
async def unlink_task(process_id: int, stage_id: int, task_id: int):
    try:
        await api.delete(f"/organizer/interview-stages/{stage_id}/tasks/{task_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/tasks/new")
async def create_and_link_task(process_id: int, stage_id: int, title: Annotated[str, Form()]):
    try:
        task = await api.post("/organizer/tasks", json={"title": title})
        await api.post(f"/organizer/interview-stages/{stage_id}/tasks/{task['id']}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/notes/{note_id}/link")
async def link_note(process_id: int, stage_id: int, note_id: int):
    try:
        await api.post(f"/organizer/interview-stages/{stage_id}/notes/{note_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/notes/{note_id}/unlink")
async def unlink_note(process_id: int, stage_id: int, note_id: int):
    try:
        await api.delete(f"/organizer/interview-stages/{stage_id}/notes/{note_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/notes/new")
async def create_and_link_note(process_id: int, stage_id: int, title: Annotated[str, Form()]):
    try:
        note = await api.post("/organizer/notes", json={"title": title})
        await api.post(f"/organizer/interview-stages/{stage_id}/notes/{note['id']}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/contacts/{contact_id}/link")
async def link_contact(process_id: int, stage_id: int, contact_id: int, role: Annotated[str, Form()] = ""):
    try:
        await api.post(f"/organizer/interview-stages/{stage_id}/contacts/{contact_id}", json={"role": role or None})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/contacts/{contact_id}/unlink")
async def unlink_contact(process_id: int, stage_id: int, contact_id: int):
    try:
        await api.delete(f"/organizer/interview-stages/{stage_id}/contacts/{contact_id}")
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/contacts/new")
async def create_and_link_contact(process_id: int, stage_id: int, name: Annotated[str, Form()], role: Annotated[str, Form()] = ""):
    try:
        contact = await api.post("/organizer/contacts", json={"name": name})
        await api.post(f"/organizer/interview-stages/{stage_id}/contacts/{contact['id']}", json={"role": role or None})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/event/{event_id}/link")
async def link_event(process_id: int, stage_id: int, event_id: int):
    try:
        await api.patch(f"/organizer/interview-stages/{stage_id}", json={"calendar_event_id": event_id})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/event/unlink")
async def unlink_event(process_id: int, stage_id: int):
    try:
        await api.patch(f"/organizer/interview-stages/{stage_id}", json={"calendar_event_id": None})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)


@router.post("/{process_id}/stages/{stage_id}/event/new")
async def create_and_link_event(
    process_id: int,
    stage_id: int,
    title: Annotated[str, Form()],
    start_datetime: Annotated[str, Form()],
    end_datetime: Annotated[str, Form()],
):
    try:
        event = await api.post("/organizer/calendar-events", json={
            "title": title, "start_datetime": start_datetime, "end_datetime": end_datetime,
        })
        await api.patch(f"/organizer/interview-stages/{stage_id}", json={"calendar_event_id": event["id"]})
    except httpx.HTTPError:
        pass
    return RedirectResponse(url=f"/interviews/{process_id}", status_code=303)
