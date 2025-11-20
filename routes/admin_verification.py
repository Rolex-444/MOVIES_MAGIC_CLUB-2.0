# routes/admin_verification.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from .admin_auth import is_admin  # ⭐ ADD THIS IMPORT

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin/verification", response_class=HTMLResponse)
async def admin_verification_settings(request: Request):
    """
    Admin page to manage verification settings.
    """
    # ⭐ ADD AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_verification.html",
            {
                "request": request,
                "message": "Database not connected",
                "enabled": True,
                "free_limit": 3,
                "valid_minutes": 1440,
            },
        )
    
    # Fetch current settings from DB
    settings = await db["verification_settings"].find_one({"_id": "default"})
    
    if not settings:
        # Default values
        settings = {
            "enabled": True,
            "free_limit": 3,
            "valid_minutes": 1440,
        }
    
    return templates.TemplateResponse(
        "admin_verification.html",
        {
            "request": request,
            "enabled": settings.get("enabled", True),
            "free_limit": settings.get("free_limit", 3),
            "valid_minutes": settings.get("valid_minutes", 1440),
        },
    )


@router.post("/admin/verification", response_class=HTMLResponse)
async def admin_verification_update(
    request: Request,
    enabled: str = Form("off"),  # checkbox sends "on" if checked
    free_limit: int = Form(3),
    valid_minutes: int = Form(1440),
):
    """
    Update verification settings.
    """
    # ⭐ ADD AUTHENTICATION CHECK
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
    
    settings = {
        "_id": "default",
        "enabled": enabled_bool,
        "free_limit": free_limit,
        "valid_minutes": valid_minutes,
    }
    
    await db["verification_settings"].update_one(
        {"_id": "default"},
        {"$set": settings},
        upsert=True,
    )
    
    return RedirectResponse(
        "/admin/verification?message=Settings+updated+successfully",
        status_code=303,
)
    
