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


# ---------- MOVIES ADMIN: LIST + SEARCH + ADD ----------


@router.get("/admin/movies", response_class=HTMLResponse)
async def admin_movies_dashboard(request: Request, message: str = ""):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    q = request.query_params.get("q", "").strip()
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_movies.html",
            {
                "request": request,
                "message": "MongoDB not connected",
                "q": q,
                "total_movies": 0,
                "tamil_count": 0,
                "telugu_count": 0,
                "hindi_count": 0,
                "malayalam_count": 0,
                "kannada_count": 0,
                "movies": [],
            },
        )

    movies_col = db["movies"]

    total_movies = await movies_col.count_documents({})
    tamil_count = await movies_col.count_documents({"language": "Tamil"})
    telugu_count = await movies_col.count_documents({"language": "Telugu"})
    hindi_count = await movies_col.count_documents({"language": "Hindi"})
    malayalam_count = await movies_col.count_documents({"language": "Malayalam"})
    kannada_count = await movies_col.count_documents({"language": "Kannada"})

    query = {}
    if q:
        query = {"title": {"$regex": q, "$options": "i"}}

    cursor = movies_col.find(query).sort("_id", -1).limit(50)
    movies = [
        {
            "id": str(doc.get("_id")),
            "title": doc.get("title", "Untitled"),
            "year": doc.get("year"),
            "language": doc.get("language"),
            "quality": doc.get("quality", "HD"),
        }
        async for doc in cursor
    ]

    return templates.TemplateResponse(
        "admin_movies.html",
        {
            "request": request,
            "message": message,
            "q": q,
            "total_movies": total_movies,
            "tamil_count": tamil_count,
            "telugu_count": telugu_count,
            "hindi_count": hindi_count,
            "malayalam_count": malayalam_count,
            "kannada_count": kannada_count,
            "movies": movies,
        },
    )


@router.post("/admin/movies", response_class=HTMLResponse)
async def admin_create_movie(
    request: Request,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form("HD"),
    category: str = Form(""),
    watch_url: str = Form(""),
    download_url: str = Form(""),
    languages: List[str] = Form(default=[]),  # checkbox languages
    description: str = Form(""),
    poster: UploadFile = File(None),
):
    """
    Create movie: primary language = first checked language, others in languages[].
    """
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            "/admin/movies?message=MongoDB+not+connected",
            status_code=303,
        )

    poster_path = None
    if poster and poster.filename:
        poster_dir = os.path.join("static", "posters")
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

    primary_language = languages[0] if languages else "Tamil"

    movie_doc = {
        "title": title,
        "year": year_int,
        "language": primary_language,
        "languages": languages,
        "quality": quality or "HD",
        "category": category,
        "watch_url": watch_url,
        "download_url": download_url,
        "poster_path": poster_path,
        "description": description,
        "created_at": datetime.utcnow(),
    }

    await db["movies"].insert_one(movie_doc)

    return RedirectResponse(
        "/admin/movies?message=Movie+saved+successfully+%E2%9C%85",
        status_code=303,
    )


# ---------- MOVIES ADMIN: EDIT + DELETE ----------


@router.get("/admin/movies/{movie_id}/edit", response_class=HTMLResponse)
async def admin_edit_movie_form(request: Request, movie_id: str):
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
        movie = await db["movies"].find_one({"_id": oid})
    except Exception:
        movie = None

    if not movie:
        return RedirectResponse(
            "/admin/movies?message=Movie+not+found",
            status_code=303,
        )

    movie_ctx = {
        "id": str(movie.get("_id")),
        "title": movie.get("title", ""),
        "year": movie.get("year") or "",
        "language": movie.get("language", "Tamil"),
        "quality": movie.get("quality", "HD"),
        "category": movie.get("category", ""),
        "watch_url": movie.get("watch_url", ""),
        "download_url": movie.get("download_url", ""),
        "languages": movie.get("languages", []),
        "description": movie.get("description", ""),
        "poster_path": movie.get("poster_path"),
    }

    return templates.TemplateResponse(
        "admin_edit_movie.html",
        {"request": request, "movie": movie_ctx},
    )


@router.post("/admin/movies/{movie_id}/edit", response_class=HTMLResponse)
async def admin_edit_movie(
    request: Request,
    movie_id: str,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form("HD"),
    category: str = Form(""),
    watch_url: str = Form(""),
    download_url: str = Form(""),
    languages: List[str] = Form(default=[]),
    description: str = Form(""),
    poster: UploadFile = File(None),
):
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
    except Exception:
        return RedirectResponse(
            "/admin/movies?message=Invalid+movie+id",
            status_code=303,
        )

    primary_language = languages[0] if languages else "Tamil"

    update = {
        "title": title,
        "language": primary_language,
        "quality": quality or "HD",
        "category": category,
        "watch_url": watch_url,
        "download_url": download_url,
        "languages": languages,
        "description": description,
    }

    if year.strip():
        try:
            update["year"] = int(year)
        except ValueError:
            update["year"] = None
    else:
        update["year"] = None

    if poster and poster.filename:
        poster_dir = os.path.join("static", "posters")
        os.makedirs(poster_dir, exist_ok=True)
        ext = os.path.splitext(poster.filename)[1].lower()
        filename = f"{uuid4().hex}{ext}"
        filepath = os.path.join(poster_dir, filename)
        content = await poster.read()
        with open(filepath, "wb") as f:
            f.write(content)
        poster_path = f"posters/{filename}"
        update["poster_path"] = poster_path

    await db["movies"].update_one({"_id": oid}, {"$set": update})

    return RedirectResponse(
        "/admin/movies?message=Movie+updated+successfully",
        status_code=303,
    )


@router.post("/admin/movies/{movie_id}/delete")
async def admin_delete_movie(request: Request, movie_id: str):
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
        await db["movies"].delete_one({"_id": oid})
        msg = "Movie+deleted+successfully"
    except Exception:
        msg = "Failed+to+delete+movie"

    return RedirectResponse(f"/admin/movies?message={msg}", status_code=303)
        
