# routes/admin_verification.py

from datetime import datetime
from bson import ObjectId
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from .admin_auth import is_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def _prepare_verification_for_template(doc: dict) -> dict:
    """Convert MongoDB verification doc to template-friendly format"""
    return {
        "id": str(doc.get("_id")),
        "type": doc.get("type", "movie"),
        "title": doc.get("title", "Untitled"),
        "year": doc.get("year"),
        "language": doc.get("language"),
        "languages": doc.get("languages", []),
        "quality": doc.get("quality", "HD"),
        "category": doc.get("category"),
        "poster_path": doc.get("poster_path"),
        "watch_url": doc.get("watch_url"),
        "download_url": doc.get("download_url"),
        "qualities": doc.get("qualities", {}),
        "description": doc.get("description", ""),
        "submitted_by": doc.get("submitted_by", "Anonymous"),
        "submitted_at": doc.get("submitted_at"),
        "status": doc.get("status", "pending"),
    }

@router.get("/admin/verification", response_class=HTMLResponse)
async def admin_verification_dashboard(request: Request):
    """Show pending verification requests"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_verification.html",
            {"request": request, "message": "MongoDB not connected", "verifications": []},
        )
    
    # Fetch pending verifications
    verifications_cursor = db["verifications"].find({"status": "pending"}).sort("submitted_at", -1)
    raw_verifications = await verifications_cursor.to_list(length=100)
    
    # Convert to template format
    verifications = [_prepare_verification_for_template(v) for v in raw_verifications]
    
    return templates.TemplateResponse(
        "admin_verification.html",
        {
            "request": request,
            "verifications": verifications,
            "total_pending": len(verifications),
        },
    )

@router.post("/admin/verification/approve/{verification_id}")
async def approve_verification(request: Request, verification_id: str):
    """Approve a verification request"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/verification?message=MongoDB+not+connected",
            status_code=303,
        )
    
    try:
        oid = ObjectId(verification_id)
    except:
        return RedirectResponse(
            "/admin/verification?message=Invalid+verification+ID",
            status_code=303,
        )
    
    # Get the verification request
    verification = await db["verifications"].find_one({"_id": oid, "status": "pending"})
    if not verification:
        return RedirectResponse(
            "/admin/verification?message=Verification+not+found",
            status_code=303,
        )
    
    # Copy to movies collection
    movie_data = {
        "title": verification["title"],
        "year": verification.get("year"),
        "language": verification.get("language"),
        "languages": verification.get("languages", []),
        "quality": verification.get("quality", "HD"),
        "category": verification.get("category"),
        "watch_url": verification.get("watch_url"),
        "download_url": verification.get("download_url"),
        "qualities": verification.get("qualities", {}),
        "poster_path": verification.get("poster_path"),
        "description": verification.get("description", ""),
        "is_multi_dubbed": verification.get("is_multi_dubbed", False),
        "created_at": verification.get("submitted_at"),
    }
    
    await db["movies"].insert_one(movie_data)
    
    # Update verification status
    await db["verifications"].update_one(
        {"_id": oid},
        {"$set": {"status": "approved", "reviewed_at": datetime.utcnow()}}
    )
    
    return RedirectResponse(
        "/admin/verification?message=Verification+approved+successfully+%E2%9C%85",
        status_code=303,
    )

@router.post("/admin/verification/reject/{verification_id}")
async def reject_verification(request: Request, verification_id: str):
    """Reject a verification request"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/verification?message=MongoDB+not+connected",
            status_code=303,
        )
    
    try:
        oid = ObjectId(verification_id)
    except:
        return RedirectResponse(
            "/admin/verification?message=Invalid+verification+ID",
            status_code=303,
        )
    
    # Update verification status
    result = await db["verifications"].update_one(
        {"_id": oid, "status": "pending"},
        {"$set": {"status": "rejected", "reviewed_at": datetime.utcnow()}}
    )
    
    if result.modified_count == 0:
        return RedirectResponse(
            "/admin/verification?message=Verification+not+found",
            status_code=303,
        )
    
    return RedirectResponse(
        "/admin/verification?message=Verification+rejected+%E2%9D%8C",
        status_code=303,
    )
    
