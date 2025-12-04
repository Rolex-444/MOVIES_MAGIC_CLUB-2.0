"""
Admin Automation Routes
Add this to your FastAPI app
"""
from fastapi import APIRouter, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import sys
sys.path.append('..')  # To import automation module

from automation.movie_processor import MovieProcessor
from .admin_auth import is_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/admin/automation", response_class=HTMLResponse)
async def automation_dashboard(request: Request):
    """Show automation dashboard"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    return templates.TemplateResponse(
        "admin_automation.html",
        {"request": request}
    )


@router.post("/admin/automation/quick-add")
async def quick_add_movie(
    request: Request,
    background_tasks: BackgroundTasks,
    magnet_link: str = Form(...),
    movie_title: str = Form(...),
    year: str = Form(None)
):
    """Quick add single movie via magnet link"""
    if not is_admin(request):
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    
    try:
        year_int = int(year) if year and year.strip() else None
    except:
        year_int = None
    
    # Process in background
    background_tasks.add_task(
        process_movie_background,
        magnet_link,
        movie_title,
        year_int
    )
    
    return JSONResponse({
        "success": True,
        "message": f"Processing started for: {movie_title}",
        "status": "Background task started"
    })


@router.post("/admin/automation/auto-scan")
async def auto_scan_tamilmv(
    request: Request,
    background_tasks: BackgroundTasks,
    limit: int = Form(10)
):
    """Automatically scan TamilMV and add new movies"""
    if not is_admin(request):
        return JSONResponse({"success": False, "error": "Unauthorized"}, status_code=401)
    
    # Run scan in background
    background_tasks.add_task(
        auto_scan_background,
        limit
    )
    
    return JSONResponse({
        "success": True,
        "message": f"Auto-scan started (scanning {limit} movies)",
        "status": "Background task started"
    })


async def process_movie_background(magnet_link: str, title: str, year: int):
    """Background task to process single movie"""
    try:
        processor = MovieProcessor()
        result = await processor.process_single_movie(magnet_link, title, year)
        
        if result["success"]:
            print(f"✅ Background: Movie added - {title}")
        else:
            print(f"❌ Background: Failed - {title}: {result['errors']}")
    
    except Exception as e:
        print(f"❌ Background error: {e}")


async def auto_scan_background(limit: int):
    """Background task to auto-scan TamilMV"""
    try:
        processor = MovieProcessor()
        summary = await processor.auto_scan_tamilmv(limit)
        print(f"✅ Auto-scan complete: {summary}")
    
    except Exception as e:
        print(f"❌ Auto-scan error: {e}")
