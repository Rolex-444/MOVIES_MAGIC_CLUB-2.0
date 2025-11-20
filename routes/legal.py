# routes/legal.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/disclaimer", response_class=HTMLResponse)
async def disclaimer_page(request: Request):
    """
    Copyright disclaimer page
    """
    return templates.TemplateResponse(
        "disclaimer.html",
        {"request": request, "active_tab": "legal"},
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """
    Privacy policy page
    """
    return templates.TemplateResponse(
        "privacy.html",
        {"request": request, "active_tab": "legal"},
    )


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """
    Terms and conditions page
    """
    return templates.TemplateResponse(
        "terms.html",
        {"request": request, "active_tab": "legal"},
    )
