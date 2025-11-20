# routes/admin_movies.py

import os
from datetime import datetime
from typing import List
from uuid import uuid4
from bson import ObjectId
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from .admin_auth import is_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ⭐ HELPER: Convert MongoDB doc to template format
def _prepare_movie_for_template(doc: dict) -> dict:
    """Convert MongoDB movie doc to template-friendly format"""
    return {
        "id": str(doc.get("_id")),
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
        "is_multi_dubbed": doc.get("is_multi_dubbed", False),
        "created_at": doc.get("created_at"),
    }

# ---------- ADMIN DASHBOARD ----------
@router.get("/admin/movies", response_class=HTMLResponse)
async def admin_movies_dashboard(request: Request, message: str = "", q: str = ""):
    """Main admin dashboard for movies"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_movies.html",
            {
                "request": request,
                "message": "MongoDB not connected",
                "q": q,
                "movies": [],
                "total_movies": 0,
                "tamil_count": 0,
                "telugu_count": 0,
                "hindi_count": 0,
            },
        )
    
    # Build query
    query = {}
    if q.strip():
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
            {"language": {"$regex": q, "$options": "i"}},
        ]
    
    # Get movies
    movies_cursor = db["movies"].find(query).sort("created_at", -1)
    raw_movies = await movies_cursor.to_list(length=100)
    
    # ⭐ Convert to template format
    movies = [_prepare_movie_for_template(m) for m in raw_movies]
    
    # Get language counts
    tamil_count = await db["movies"].count_documents({"language": "Tamil"})
    telugu_count = await db["movies"].count_documents({"language": "Telugu"})
    hindi_count = await db["movies"].count_documents({"language": "Hindi"})
    
    return templates.TemplateResponse(
        "admin_movies.html",
        {
            "request": request,
            "message": message,
            "q": q,
            "movies": movies,
            "total_movies": len(movies),
            "tamil_count": tamil_count,
            "telugu_count": telugu_count,
            "hindi_count": hindi_count,
        },
    )

# ---------- CREATE MOVIE ----------
@router.post("/admin/movies", response_class=HTMLResponse)
async def admin_create_movie(
    request: Request,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form("HD"),
    category: str = Form(""),
    watch_url: str = Form(""),
    download_url: str = Form(""),
    # ⭐ QUALITY PARAMETERS - CRITICAL!
    quality_480p_watch: str = Form(""),
    quality_480p_download: str = Form(""),
    quality_720p_watch: str = Form(""),
    quality_720p_download: str = Form(""),
    quality_1080p_watch: str = Form(""),
    quality_1080p_download: str = Form(""),
    quality_2k_watch: str = Form(""),
    quality_2k_download: str = Form(""),
    quality_4k_watch: str = Form(""),
    quality_4k_download: str = Form(""),
    # Multi-language support
    languages: List[str] = Form(default=[]),
    description: str = Form(""),
    poster: UploadFile = File(None),
):
    """Create new movie"""
    
    # ⭐ DEBUG LOGGING - ADD THIS AT THE TOP
    print("=== DEBUG CREATE: Quality fields received ===")
    print(f"480p watch: '{quality_480p_watch}'")
    print(f"480p download: '{quality_480p_download}'")
    print(f"qualities dict before building: {[quality_480p_watch, quality_480p_download]}")
    
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/movies?message=MongoDB+not+connected",
            status_code=303,
        )

    # Handle poster
    poster_path = None
    if poster and poster.filename:
        poster_dir = "static/posters"
        os.makedirs(poster_dir, exist_ok=True)
        ext = os.path.splitext(poster.filename)[1].lower()
        filename = f"{uuid4().hex}{ext}"
        filepath = os.path.join(poster_dir, filename)
        content = await poster.read()
        with open(filepath, "wb") as f:
            f.write(content)
        poster_path = f"posters/{filename}"

    year_int = None
    if year.strip():
        try:
            year_int = int(year)
        except ValueError:
            year_int = None

    # ⭐ BUILD QUALITIES DICT
    qualities = {}
    
    if quality_480p_watch.strip() or quality_480p_download.strip():
        qualities["480p"] = {
            "watch_url": quality_480p_watch.strip() or None,
            "download_url": quality_480p_download.strip() or None,
        }
    
    if quality_720p_watch.strip() or quality_720p_download.strip():
        qualities["720p"] = {
            "watch_url": quality_720p_watch.strip() or None,
            "download_url": quality_720p_download.strip() or None,
        }
    
    if quality_1080p_watch.strip() or quality_1080p_download.strip():
        qualities["1080p"] = {
            "watch_url": quality_1080p_watch.strip() or None,
            "download_url": quality_1080p_download.strip() or None,
        }
    
    if quality_2k_watch.strip() or quality_2k_download.strip():
        qualities["2k"] = {
            "watch_url": quality_2k_watch.strip() or None,
            "download_url": quality_2k_download.strip() or None,
        }
    
    if quality_4k_watch.strip() or quality_4k_download.strip():
        qualities["4k"] = {
            "watch_url": quality_4k_watch.strip() or None,
            "download_url": quality_4k_download.strip() or None,
        }

    # ⭐ DEBUG LOGGING - SHOW FINAL DICT
    print(f"Final qualities dict: {qualities}")

    quality_label = ", ".join(qualities.keys()) if qualities else quality
    primary_language = languages[0] if languages else "Tamil"
    is_multi_dubbed = len(languages) > 1

    movie_doc = {
        "title": title.strip(),
        "year": year_int,
        "language": primary_language,
        "languages": languages,
        "quality": quality_label,
        "category": category.strip() or None,
        "watch_url": watch_url.strip() or None,
        "download_url": download_url.strip() or None,
        "qualities": qualities,
        "poster_path": poster_path,
        "description": description.strip(),
        "is_multi_dubbed": is_multi_dubbed,
        "created_at": datetime.utcnow(),
    }

    await db["movies"].insert_one(movie_doc)
    return RedirectResponse(
        "/admin/movies?message=Movie+added+successfully+%E2%9C%85",
        status_code=303,
    )

# ---------- EDIT MOVIE (SHOW FORM) ----------
@router.get("/admin/movies/edit/{movie_id}", response_class=HTMLResponse)
async def admin_edit_movie_form(request: Request, movie_id: str):
    """Show edit form for a movie"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/movies?message=MongoDB+not+connected",
            status_code=303,
        )

    try:
        movie_doc = await db["movies"].find_one({"_id": ObjectId(movie_id)})
    except:
        return RedirectResponse(
            "/admin/movies?message=Invalid+movie+ID",
            status_code=303,
        )

    if not movie_doc:
        return RedirectResponse(
            "/admin/movies?message=Movie+not+found",
            status_code=303,
        )

    # ⭐ Convert to template format
    movie = _prepare_movie_for_template(movie_doc)

    return templates.TemplateResponse(
        "admin_movies.html",
        {
            "request": request,
            "movie": movie,
        },
    )

# ---------- EDIT MOVIE (HANDLE SUBMIT) ----------
@router.post("/admin/movies/edit/{movie_id}", response_class=HTMLResponse)
async def admin_update_movie(
    request: Request,
    movie_id: str,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form("HD"),
    category: str = Form(""),
    watch_url: str = Form(""),
    download_url: str = Form(""),
    # ⭐ QUALITY PARAMETERS - CRITICAL!
    quality_480p_watch: str = Form(""),
    quality_480p_download: str = Form(""),
    quality_720p_watch: str = Form(""),
    quality_720p_download: str = Form(""),
    quality_1080p_watch: str = Form(""),
    quality_1080p_download: str = Form(""),
    quality_2k_watch: str = Form(""),
    quality_2k_download: str = Form(""),
    quality_4k_watch: str = Form(""),
    quality_4k_download: str = Form(""),
    # Multi-language support
    languages: List[str] = Form(default=[]),
    description: str = Form(""),
    poster: UploadFile = File(None),
):
    """Update an existing movie"""
    
    # ⭐ DEBUG LOGGING - ADD THIS AT THE TOP
    print("=== DEBUG UPDATE: Quality fields received ===")
    print(f"480p watch: '{quality_480p_watch}'")
    print(f"480p download: '{quality_480p_download}'")
    print(f"qualities dict before building: {[quality_480p_watch, quality_480p_download]}")
    
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/movies?message=MongoDB+not+connected",
            status_code=303,
        )

    try:
        oid = ObjectId(movie_id)
    except:
        return RedirectResponse(
            "/admin/movies?message=Invalid+movie+ID",
            status_code=303,
        )

    # Handle poster upload
    poster_path = None
    if poster and poster.filename:
        poster_dir = "static/posters"
        os.makedirs(poster_dir, exist_ok=True)
        ext = os.path.splitext(poster.filename)[1].lower()
        filename = f"{uuid4().hex}{ext}"
        filepath = os.path.join(poster_dir, filename)
        content = await poster.read()
        with open(filepath, "wb") as f:
            f.write(content)
        poster_path = f"posters/{filename}"

    year_int = None
    if year.strip():
        try:
            year_int = int(year)
        except ValueError:
            year_int = None

    # ⭐ BUILD QUALITIES DICT
    qualities = {}
    
    if quality_480p_watch.strip() or quality_480p_download.strip():
        qualities["480p"] = {
            "watch_url": quality_480p_watch.strip() or None,
            "download_url": quality_480p_download.strip() or None,
        }
    
    if quality_720p_watch.strip() or quality_720p_download.strip():
        qualities["720p"] = {
            "watch_url": quality_720p_watch.strip() or None,
            "download_url": quality_720p_download.strip() or None,
        }
    
    if quality_1080p_watch.strip() or quality_1080p_download.strip():
        qualities["1080p"] = {
            "watch_url": quality_1080p_watch.strip() or None,
            "download_url": quality_1080p_download.strip() or None,
        }
    
    if quality_2k_watch.strip() or quality_2k_download.strip():
        qualities["2k"] = {
            "watch_url": quality_2k_watch.strip() or None,
            "download_url": quality_2k_download.strip() or None,
        }
    
    if quality_4k_watch.strip() or quality_4k_download.strip():
        qualities["4k"] = {
            "watch_url": quality_4k_watch.strip() or None,
            "download_url": quality_4k_download.strip() or None,
        }

    # ⭐ DEBUG LOGGING - SHOW FINAL DICT
    print(f"Final qualities dict: {qualities}")

    quality_label = ", ".join(qualities.keys()) if qualities else quality
    primary_language = languages[0] if languages else "Tamil"
    is_multi_dubbed = len(languages) > 1

    # Update data
    update_data = {
        "title": title.strip(),
        "year": year_int,
        "language": primary_language,
        "languages": languages,
        "quality": quality_label,
        "category": category.strip() or None,
        "watch_url": watch_url.strip() or None,
        "download_url": download_url.strip() or None,
        "qualities": qualities,
        "description": description.strip(),
        "is_multi_dubbed": is_multi_dubbed,
    }

    if poster_path:
        update_data["poster_path"] = poster_path

    result = await db["movies"].update_one(
        {"_id": oid},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        return RedirectResponse(
            "/admin/movies?message=Movie+not+found+or+no+changes",
            status_code=303,
        )

    return RedirectResponse(
        "/admin/movies?message=Movie+updated+successfully+%E2%9C%85",
        status_code=303,
    )

# ---------- DELETE MOVIE ----------
@router.get("/admin/movies/delete/{movie_id}")
async def admin_delete_movie(request: Request, movie_id: str):
    """Delete a movie"""
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/movies?message=MongoDB+not+connected",
            status_code=303,
        )

    try:
        oid = ObjectId(movie_id)
    except:
        return RedirectResponse(
            "/admin/movies?message=Invalid+movie+ID",
            status_code=303,
        )

    result = await db["movies"].delete_one({"_id": oid})
    
    if result.deleted_count == 0:
        return RedirectResponse(
            "/admin/movies?message=Movie+not+found",
            status_code=303,
        )

    return RedirectResponse(
        "/admin/movies?message=Movie+deleted+successfully+%F0%9F%97%91",
        status_code=303,
)
            
