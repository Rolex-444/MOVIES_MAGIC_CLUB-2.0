# routes/admin_auth.py

import os

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_form(request: Request):
    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": ""},
    )


@router.post("/admin/login", response_class=HTMLResponse)
async def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["is_admin"] = True
        return RedirectResponse("/admin/movies", status_code=303)

    return templates.TemplateResponse(
        "admin_login.html",
        {"request": request, "error": "Invalid password"},
    )


@router.get("/admin/logout")
async def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
    
