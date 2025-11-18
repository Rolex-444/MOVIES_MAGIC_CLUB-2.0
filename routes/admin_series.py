# routes/series.py

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_db
from verification_utils import (
    should_require_verification,
    increment_free_used,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _series_to_ctx(doc: dict) -> dict:
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title", "Untitled series"),
        "year": doc.get("year"),
        "language": doc.get("language"),
        "poster_path": doc.get("poster_path"),
        "watch_url": doc.get("watch_url"),
        "download_url": doc.get("download_url"),
        "description": doc.get("description", ""),
        "languages": doc.get("languages", []),
    }


# ---------- SERIES HOME ----------


@router.get("/series", response_class=HTMLResponse)
async def series_home(request: Request):
    db = get_db()
    latest_series: List[dict] = []

    if db is not None:
        col = db["series"]
        cursor = col.find().sort("_id", -1).limit(30)
        latest_series = [_series_to_ctx(doc) async for doc in cursor]

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

    languages = series_doc.get("languages") or []
    primary_language = series_doc.get("language") or (languages[0] if languages else "Tamil")
    audio_text = ", ".join(languages) if languages else primary_language

    series_ctx = {
        "id": str(series_doc.get("_id")),
        "title": series_doc.get("title", "Untitled series"),
        "year": series_doc.get("year"),
        "language": primary_language,
        "poster_path": series_doc.get("poster_path"),
        "watch_url": series_doc.get("watch_url"),
        "download_url": series_doc.get("download_url"),
        "description": series_doc.get("description", ""),
        "audio": audio_text,
        "languages": languages,
    }

    return templates.TemplateResponse(
        "series_detail.html",
        {
            "request": request,
            "series": series_ctx,
            "active_tab": "series",
        },
    )


# ---------- SERIES WATCH / DOWNLOAD WITH VERIFICATION ----------


@router.get("/series/{series_id}/watch")
async def series_watch(request: Request, series_id: str):
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/series/{series_id}/watch",
            status_code=303,
        )

    await increment_free_used(request)

    db = get_db()
    series_doc: Optional[dict] = None
    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc or not series_doc.get("watch_url"):
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    return RedirectResponse(url=series_doc["watch_url"], status_code=302)


@router.get("/series/{series_id}/download")
async def series_download(request: Request, series_id: str):
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/series/{series_id}/download",
            status_code=303,
        )

    await increment_free_used(request)

    db = get_db()
    series_doc: Optional[dict] = None
    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc or not series_doc.get("download_url"):
        return RedirectResponse(url=f"/series/{series_id}", status_code=303)

    return RedirectResponse(url=series_doc["download_url"], status_code=302)
        
