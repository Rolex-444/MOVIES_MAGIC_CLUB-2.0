# routes/admin_movies.py

from datetime import datetime
from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx

from db import get_db
from .admin_auth import is_admin

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.post("/admin/movies", response_class=HTMLResponse)
async def admin_create_movie(
    request: Request,
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
        return RedirectResponse("/admin/movies?message=MongoDB+not+connected", status_code=303)

    # Handle poster upload (to Telegram)
    poster_path = None
    if poster and poster.filename:
        try:
            content = await poster.read()
            async with httpx.AsyncClient() as client:
                files = {
                    "image": (poster.filename, content, poster.content_type or "image/jpeg"),
                }
                data = {
                    "movie_title": title,
                    "description": description or "",
                }
                resp = await client.post("http://127.0.0.1:8000/api/poster/upload", data=data, files=files, timeout=30)
                resp_data = resp.json()
                if resp_data.get("success"):
                    poster_path = resp_data.get("url")
        except Exception as e:
            print(f"[ADMIN] Poster upload error: {e}")

    year_int = None
    if year.strip():
        try:
            year_int = int(year)
        except ValueError:
            year_int = None

    primary_language = languages[0] if languages else "Tamil"

    # ---- NEW: Only ONE document per (title, year) ----
    existing = await db["movies"].find_one({"title": title, "year": year_int})
    movie_doc = {
        "title": title,
        "year": year_int,
        "language": primary_language,
        "languages": languages,
        "audio_languages": languages,
        "quality": quality or "HD",
        "category": category,
        "watch_url": watch_url,
        "download_url": download_url,
        "poster_path": poster_path,
        "description": description,
        "created_at": datetime.utcnow(),
    }
    if existing:
        # Merge languages
        merged_languages = list(set(existing.get("languages", [])) | set(languages))
        movie_doc["languages"] = merged_languages
        movie_doc["audio_languages"] = merged_languages
        # Only update blank fields if new data given
        for key in movie_doc:
            if movie_doc[key]:  # Only update if value present
                await db["movies"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": {key: movie_doc[key]}}
                )
        return RedirectResponse(
            "/admin/movies?message=Movie+updated+successfully",
            status_code=303,
        )
    # Safe to insert new
    await db["movies"].insert_one(movie_doc)
    return RedirectResponse(
        "/admin/movies?message=Movie+saved+successfully+%E2%9C%85",
        status_code=303,
        )
                                
