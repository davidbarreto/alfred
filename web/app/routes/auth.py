from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.templates_config import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    password: Annotated[str, Form()],
):
    if password == get_settings().web_password:
        request.session["authenticated"] = True
        next_url = request.query_params.get("next", "/")
        return RedirectResponse(next_url, status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": "Incorrect password."}, status_code=401)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)
