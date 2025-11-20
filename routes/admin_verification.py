# routes/admin_verification.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from config import (
    VERIFICATION_DEFAULT_ENABLED,
    VERIFICATION_DEFAULT_FREE_LIMIT,
    VERIFICATION_DEFAULT_VALID_MINUTES,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def is_admin(request: Request) -> bool:
    """Check if current session is admin."""
    return request.session.get("admin_logged_in", False)


@router.get("/admin/verification", response_class=HTMLResponse)
async def admin_verification_settings(request: Request):
    """
    Admin page to manage 3-free-movies verification settings.
    """
    # Authentication check
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    message = request.query_params.get("message", "")
    
    if db is None:
        return templates.TemplateResponse(
            "admin_verification.html",
            {
                "request": request,
                "message": "Database not connected",
                "enabled": VERIFICATION_DEFAULT_ENABLED,
                "free_limit": VERIFICATION_DEFAULT_FREE_LIMIT,
                "valid_minutes": VERIFICATION_DEFAULT_VALID_MINUTES,
            },
        )
    
    # Fetch current settings from correct collection
    settings = await db["settings"].find_one({"_id": "verification"})
    
    if not settings:
        # Use config defaults
        settings = {
            "enabled": VERIFICATION_DEFAULT_ENABLED,
            "free_limit": VERIFICATION_DEFAULT_FREE_LIMIT,
            "valid_minutes": VERIFICATION_DEFAULT_VALID_MINUTES,
        }
    
    return templates.TemplateResponse(
        "admin_verification.html",
        {
            "request": request,
            "message": message,
            "enabled": settings.get("enabled", VERIFICATION_DEFAULT_ENABLED),
            "free_limit": settings.get("free_limit", VERIFICATION_DEFAULT_FREE_LIMIT),
            "valid_minutes": settings.get("valid_minutes", VERIFICATION_DEFAULT_VALID_MINUTES),
        },
    )


@router.post("/admin/verification", response_class=HTMLResponse)
async def admin_verification_update(
    request: Request,
    enabled: str = Form("off"),  # checkbox sends "on" if checked, "off" if unchecked
    free_limit: int = Form(3),
    valid_minutes: int = Form(1440),
):
    """
    Update 3-free-movies verification settings.
    """
    # Authentication check
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/verification?message=Database+not+connected",
            status_code=303,
        )
    
    # Convert checkbox value to boolean
    enabled_bool = (enabled == "on")
    
    # Save to correct collection and document ID
    await db["settings"].update_one(
        {"_id": "verification"},
        {
            "$set": {
                "enabled": enabled_bool,
                "free_limit": free_limit,
                "valid_minutes": valid_minutes,
            }
        },
        upsert=True,
    )
    
    return RedirectResponse(
        "/admin/verification?message=Settings+updated+successfully",
        status_code=303,
                )
    
