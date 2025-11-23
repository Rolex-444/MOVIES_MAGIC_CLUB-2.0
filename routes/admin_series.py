# routes/admin_series.py

import os
import shutil
from typing import List, Optional
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import httpx  # 🔹 NEW: for calling /api/poster/upload

from db import get_db
from verification_utils import should_require_verification, increment_free_used
from .admin_auth import is_admin  # ⭐ already present

router = APIRouter()

templates = Jinja2Templates(directory="templates")

# Poster upload directory (still kept, in case you need legacy local posters)
POSTER_DIR = Path("static/posters")
POSTER_DIR.mkdir(parents=True, exist_ok=True)


def _series_to_ctx(doc: dict) -> dict:
    """
    Normalize series document into a template-friendly dict.
    Supports episode-wise links.
    """
    episodes = doc.get("episodes") or []

    # Build a clean list of episodes with index for routing
    ep_list = []
    for idx, ep in enumerate(episodes):
        ep_list.append(
            {
                "index": idx,
                "number": ep.get("number") or idx + 1,
                "name": ep.get("name") or f"Episode {idx + 1}",
                "watch_url": ep.get("watch_url"),
                "download_url": ep.get("download_url"),
            }
        )

    # Primary language + audio text
    languages = doc.get("languages") or []
    primary_language = doc.get("language") or (languages[0] if languages else "Tamil")
    audio_text = ", ".join(languages) if languages else primary_language

    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title", "Untitled series"),
        "year": doc.get("year"),
        "quality": doc.get("quality"),
        "language": primary_language,
        "poster_path": doc.get("poster_path"),
        "category": doc.get("category"),
        "description": doc.get("description", ""),
        "languages": languages,
        "audio": audio_text,
        "episodes": ep_list,
    }


# ---------- SERIES HOME (tab) ----------

@router.get("/series", response_class=HTMLResponse)
async def series_home(request: Request):
    db = get_db()
    latest_series: List[dict] = []

    if db is not None:
        col = db["series"]
        cursor = col.find().sort("_id", -1).limit(20)
        latest_series = [
            _series_to_ctx(doc) for doc in await cursor.to_list(length=20)
        ]

    return templates.TemplateResponse(
        "series_index.html",
        {
            "request": request,
            "latest_series": latest_series,
            "active_tab": "series",
        },
    )


# ---------- SERIES DETAIL ----------

@router.get("/series/{series_id}", response_class=HTMLResponse)
async def series_detail(request: Request, series_id: str):
    db = get_db()
    series_doc: Optional[dict] = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc:
        return templates.TemplateResponse(
            "series_detail.html",
            {
                "request": request,
                "series": None,
                "active_tab": "series",
            },
        )

    series_ctx = _series_to_ctx(series_doc)
    return templates.TemplateResponse(
        "series_detail.html",
        {
            "request": request,
            "series": series_ctx,
            "active_tab": "series",
        },
    )


# ---------- EPISODE WATCH / DOWNLOAD (with verification) ----------

@router.get("/series/{series_id}/episode/{ep_index}/watch")
async def series_episode_watch(request: Request, series_id: str, ep_index: int):
    """
    Gate for episode Watch button.
    """
    # 1) Check verification
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/series/{series_id}/episode/{ep_index}/watch",
            status_code=303,
        )

    # 2) Count this click
    await increment_free_used(request)

    # 3) Redirect to actual episode watch_url
    db = get_db()
    series_doc: Optional[dict] = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc:
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    episodes = series_doc.get("episodes") or []
    if ep_index < 0 or ep_index >= len(episodes):
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    ep = episodes[ep_index]
    watch_url = ep.get("watch_url")
    if not watch_url:
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    return RedirectResponse(url=watch_url, status_code=302)


@router.get("/series/{series_id}/episode/{ep_index}/download")
async def series_episode_download(request: Request, series_id: str, ep_index: int):
    """
    Gate for episode Download button.
    """
    # 1) Check verification
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/series/{series_id}/episode/{ep_index}/download",
            status_code=303,
        )

    # 2) Count this click
    await increment_free_used(request)

    # 3) Redirect to actual episode download_url
    db = get_db()
    series_doc: Optional[dict] = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc:
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    episodes = series_doc.get("episodes") or []
    if ep_index < 0 or ep_index >= len(episodes):
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    ep = episodes[ep_index]
    download_url = ep.get("download_url")
    if not download_url:
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    return RedirectResponse(url=download_url, status_code=302)


# ---------- ADMIN: SERIES DASHBOARD (list + add form) ----------

@router.get("/admin/series", response_class=HTMLResponse)
async def admin_series_dashboard(request: Request):
    """
    Admin page to view all series and show the 'Add new series' form.
    """
    # ⭐ AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    series_list: List[dict] = []

    if db is not None:
        col = db["series"]
        cursor = col.find().sort("_id", -1)
        docs = await cursor.to_list(length=100)
        series_list = [_series_to_ctx(doc) for doc in docs]

    return templates.TemplateResponse(
        "admin_series.html",
        {
            "request": request,
            "series_list": series_list,
            "active_tab": "series_admin",
        },
    )


@router.post("/admin/series", response_class=HTMLResponse)
async def admin_series_create(
    request: Request,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form(""),
    category: str = Form(""),
    languages: List[str] = Form([]),
    description: str = Form(""),
    poster: UploadFile = File(None),
):
    """
    Handle 'Save series' form from admin_series.html.
    Now supports poster file upload via Telegram microservice.
    """
    # ⭐ AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_series.html",
            {
                "request": request,
                "series_list": [],
                "message": "❌ Database not connected.",
            },
        )

    # Handle poster upload via Telegram
    poster_path: Optional[str] = None

    if poster and poster.filename:
        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
                files = {
                    "image": (
                        poster.filename,
                        await poster.read(),
                        poster.content_type or "image/jpeg",
                    )
                }
                data = {
                    "movie_title": title.strip(),
                    "description": description.strip() or "",
                }
                resp = await client.post(
                    "/api/poster/upload", data=data, files=files, timeout=30
                )

            if resp.status_code == 200:
                resp_data = resp.json()
                if resp_data.get("success"):
                    poster_path = resp_data.get("url")
                else:
                    print("Series poster upload failed:", resp_data)
            else:
                print("Series poster upload HTTP error:", resp.status_code)
        except Exception as e:
            print("Series poster upload exception:", e)

    # Build document
    doc = {
        "title": title.strip(),
        "year": year.strip() or None,
        "quality": quality.strip() or None,
        "category": category.strip() or None,
        "poster_path": poster_path,
        "languages": languages,
        "description": description.strip(),
        "episodes": [],  # seasons/episodes will be added later
    }

    # Set primary language field from languages list
    if languages:
        doc["language"] = languages[0]

    await db["series"].insert_one(doc)
    return RedirectResponse(url="/admin/series", status_code=303)


# ---------- ADMIN: EDIT SERIES ----------

@router.get("/admin/series/{series_id}/edit", response_class=HTMLResponse)
async def admin_series_edit_form(request: Request, series_id: str):
    # ⭐ AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(url="/admin/series", status_code=303)

    try:
        oid = ObjectId(series_id)
    except Exception:
        return RedirectResponse(url="/admin/series", status_code=303)

    doc = await db["series"].find_one({"_id": oid})
    if not doc:
        return RedirectResponse(url="/admin/series", status_code=303)

    series_ctx = _series_to_ctx(doc)
    return templates.TemplateResponse(
        "admin_edit_series.html",
        {
            "request": request,
            "series": series_ctx,
            "active_tab": "series_admin",
        },
    )


@router.post("/admin/series/{series_id}/edit")
async def admin_series_edit_submit(
    request: Request,
    series_id: str,
    title: str = Form(...),
    year: str = Form(""),
    quality: str = Form(""),
    category: str = Form(""),
    languages: List[str] = Form([]),
    description: str = Form(""),
    poster: UploadFile = File(None),
):
    # ⭐ AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(url="/admin/series", status_code=303)

    try:
        oid = ObjectId(series_id)
    except Exception:
        return RedirectResponse(url="/admin/series", status_code=303)

    update_doc = {
        "title": title.strip(),
        "year": year.strip() or None,
        "quality": quality.strip() or None,
        "category": category.strip() or None,
        "languages": languages,
        "description": description.strip(),
    }

    if languages:
        update_doc["language"] = languages[0]

    # Optional: handle new poster upload via Telegram
    if poster and poster.filename:
        new_poster_path: Optional[str] = None
        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
                files = {
                    "image": (
                        poster.filename,
                        await poster.read(),
                        poster.content_type or "image/jpeg",
                    )
                }
                data = {
                    "movie_title": title.strip(),
                    "description": description.strip() or "",
                }
                resp = await client.post(
                    "/api/poster/upload", data=data, files=files, timeout=30
                )

            if resp.status_code == 200:
                resp_data = resp.json()
                if resp_data.get("success"):
                    new_poster_path = resp_data.get("url")
        except Exception as e:
            print("Series poster upload exception (edit):", e)

        if new_poster_path:
            update_doc["poster_path"] = new_poster_path

    await db["series"].update_one({"_id": oid}, {"$set": update_doc})
    return RedirectResponse(url="/admin/series", status_code=303)


# ---------- ADMIN: DELETE SERIES ----------

@router.post("/admin/series/{series_id}/delete")
async def admin_series_delete(request: Request, series_id: str):
    # ⭐ AUTHENTICATION CHECK
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(url="/admin/series", status_code=303)

    try:
        oid = ObjectId(series_id)
    except Exception:
        return RedirectResponse(url="/admin/series", status_code=303)

    await db["series"].delete_one({"_id": oid})
    return RedirectResponse(url="/admin/series", status_code=303)
    
