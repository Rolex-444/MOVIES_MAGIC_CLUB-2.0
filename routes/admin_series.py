# routes/admin_series.py (public series pages + episode-wise watch/download)

from typing import List, Optional

from bson import ObjectId

from fastapi import APIRouter, Request, Form
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
        "language": primary_language,
        "poster_path": doc.get("poster_path"),
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
    poster_path: str = Form(""),
    languages: List[str] = Form([]),
    description: str = Form(""),
):
    """
    Handle 'Save series' form from admin_series.html.
    """
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

    doc = {
        "title": title.strip(),
        "year": year.strip() or None,
        "quality": quality.strip() or None,
        "category": category.strip() or None,
        "poster_path": poster_path.strip() or None,
        "languages": languages,
        "description": description.strip(),
        "episodes": [],  # seasons/episodes will be added later
    }

    await db["series"].insert_one(doc)

    # Reload list after insert
    col = db["series"]
    cursor = col.find().sort("_id", -1)
    docs = await cursor.to_list(length=100)
    series_list = [_series_to_ctx(d) for d in docs]

    return templates.TemplateResponse(
        "admin_series.html",
        {
            "request": request,
            "series_list": series_list,
            "message": "✅ Series added successfully!",
            "active_tab": "series_admin",
        },
                       )
            
