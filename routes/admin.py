# routes/admin.py

import os
from datetime import datetime
from typing import List
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


# ---------- LOGIN / LOGOUT ----------


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


# ---------- DASHBOARD + CRUD ----------


@router.get("/admin/movies", response_class=HTMLResponse)
async def admin_dashboard(request: Request, message: str = ""):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_movies.html",
            {
                "request": request,
                "message": "MongoDB not connected",
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

    cursor = movies_col.find().sort("_id", -1).limit(30)
    movies: List[dict] = [
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
    language: str = Form(...),
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

    movie_doc = {
        "title": title,
        "year": year_int,
        "language": language,
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
