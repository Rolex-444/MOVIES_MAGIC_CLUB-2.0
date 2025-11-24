# routes/movies.py

from typing import List, Optional
from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from verification_utils import (
    should_require_verification,
    increment_free_used,
    get_user_verification_state,  # Added for debug
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def _movie_to_ctx(doc: dict) -> dict:
    """Normalize movie document into a template-friendly dict."""
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title", "Untitled"),
        "year": doc.get("year"),
        "language": doc.get("language"),
        "quality": doc.get("quality", "HD"),
        "category": doc.get("category"),
        "poster_path": doc.get("poster_path"),
        "watch_url": doc.get("watch_url"),
        "download_url": doc.get("download_url"),
        "languages": doc.get("languages", []),
        "description": doc.get("description", ""),
    }


# ---------- MOVIES DETAIL PAGE ----------

@router.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: str):
    """
    Renders movie_detail.html for a single movie (poster, title, description, buttons).
    """
    db = get_db()
    movie_doc: Optional[dict] = None
    if db is not None:
        try:
            oid = ObjectId(movie_id)
            movie_doc = await db["movies"].find_one({"_id": oid})
        except Exception:
            movie_doc = None

    if not movie_doc:
        return templates.TemplateResponse(
            "movie_detail.html",
            {
                "request": request,
                "movie": None,
                "active_tab": "movies",
            },
        )

    movie_ctx = _movie_to_ctx(movie_doc)
    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "movie": movie_ctx,
            "active_tab": "movies",
        },
    )


# ---------- BROWSE ALL MOVIES ----------

@router.get("/movies/browse", response_class=HTMLResponse)
async def browse_all_movies(request: Request):
    """
    Show all movies in a grid (no pagination).
    """
    db = get_db()
    movies: List[dict] = []
    if db is not None:
        # ✅ Exclude series (documents with 'seasons' field)
        cursor = db["movies"].find({"seasons": {"$exists": False}}).sort("_id", -1)
        async for doc in cursor:
            movies.append(_movie_to_ctx(doc))

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "page_title": "All Movies",
            "page_subtitle": "Browse our complete collection",
            "movies": movies,
            "active_tab": "movies",
        },
    )


# ---------- WATCH / DOWNLOAD GATES (with verification + DEBUG) ----------

@router.get("/movie/{movie_id}/watch")
async def movie_watch(request: Request, movie_id: str):
    """
    ✅ FIXED: Gate for Watch Now button - CHECK FIRST, THEN INCREMENT
    """
    print("\n" + "="*60)
    print(f"🎬 WATCH BUTTON CLICKED - Movie ID: {movie_id}")
    print("="*60)
    
    # Get state BEFORE any changes
    settings_before, state_before, _ = await get_user_verification_state(request)
    print(f"🔍 CURRENT STATE:")
    print(f"   - free_used: {state_before['free_used']}")
    print(f"   - free_limit: {settings_before['free_limit']}")
    print(f"   - enabled: {settings_before['enabled']}")
    print(f"   - verified_until: {state_before['verified_until']}")
    
    # ✅ STEP 1: CHECK VERIFICATION FIRST (before incrementing)
    needs_verify = await should_require_verification(request)
    print(f"🔍 VERIFICATION CHECK (BEFORE INCREMENT):")
    print(f"   - needs_verify: {needs_verify}")
    
    if needs_verify:
        print(f"🚨 REDIRECTING TO VERIFICATION PAGE")
        print("="*60 + "\n")
        return RedirectResponse(
            url=f"/verify/start?next=/movie/{movie_id}/watch",
            status_code=303,
        )
    
    # ✅ STEP 2: ONLY INCREMENT if not requiring verification
    await increment_free_used(request)
    print(f"✅ INCREMENT DONE - User allowed to watch")
    
    # Get state after increment (for debug)
    settings_after, state_after, _ = await get_user_verification_state(request)
    print(f"🔍 AFTER INCREMENT:")
    print(f"   - free_used: {state_after['free_used']}")
    print(f"✅ ALLOWING ACCESS TO VIDEO")
    print("="*60 + "\n")
    
    # ✅ STEP 3: Get movie and show video player page
    db = get_db()
    movie_doc: Optional[dict] = None
    if db is not None:
        try:
            oid = ObjectId(movie_id)
            movie_doc = await db["movies"].find_one({"_id": oid})
        except Exception:
            movie_doc = None
    
    if not movie_doc or not movie_doc.get("watch_url"):
        return RedirectResponse(url=f"/movie/{movie_id}", status_code=303)
    
    # ✅ STEP 4: Convert Lulu URL to embed format - handle multiple URL patterns
    watch_url = movie_doc["watch_url"]
    
    if "luluvid.com/e/" in watch_url or "lulivid.com/e/" in watch_url:
        # Already in embed format
        embed_url = watch_url
        print(f"✅ Already embed URL: {embed_url}")
    elif "luluvid.com/d/" in watch_url or "lulivid.com/d/" in watch_url:
        # Convert /d/ to /e/
        embed_url = watch_url.replace("/d/", "/e/")
        print(f"🔄 Converted /d/ to /e/: {watch_url} -> {embed_url}")
    elif "luluvid.com/" in watch_url or "lulivid.com/" in watch_url:
        # Direct video ID format (no /d/ or /e/) - add /e/ before video ID
        # Example: https://luluvid.com/g4ttoy0mlp83 -> https://luluvid.com/e/g4ttoy0mlp83
        parts = watch_url.split("/")
        video_id = parts[-1]  # Get last part (video ID)
        base_url = "/".join(parts[:-1])  # Get everything before video ID
        embed_url = f"{base_url}/e/{video_id}"
        print(f"🔄 Added /e/ to URL: {watch_url} -> {embed_url}")
    else:
        # Unknown format, use as-is
        embed_url = watch_url
        print(f"⚠️ Unknown URL format, using as-is: {embed_url}")
    
    # ✅ STEP 5: Render video player template with fullscreen support
    return templates.TemplateResponse(
        "watch_video.html",
        {
            "request": request,
            "video_url": embed_url,
            "title": movie_doc.get("title", "Watch Movie")
        }
    )


@router.get("/movie/{movie_id}/download")
async def movie_download(request: Request, movie_id: str):
    """
    ✅ FIXED: Gate for Download button - CHECK FIRST, THEN INCREMENT
    """
    print("\n" + "="*60)
    print(f"📥 DOWNLOAD BUTTON CLICKED - Movie ID: {movie_id}")
    print("="*60)
    
    # Get state BEFORE any changes
    settings_before, state_before, _ = await get_user_verification_state(request)
    print(f"🔍 CURRENT STATE:")
    print(f"   - free_used: {state_before['free_used']}")
    print(f"   - free_limit: {settings_before['free_limit']}")
    print(f"   - enabled: {settings_before['enabled']}")
    print(f"   - verified_until: {state_before['verified_until']}")
    
    # ✅ STEP 1: CHECK VERIFICATION FIRST (before incrementing)
    needs_verify = await should_require_verification(request)
    print(f"🔍 VERIFICATION CHECK (BEFORE INCREMENT):")
    print(f"   - needs_verify: {needs_verify}")
    
    if needs_verify:
        print(f"🚨 REDIRECTING TO VERIFICATION PAGE")
        print("="*60 + "\n")
        return RedirectResponse(
            url=f"/verify/start?next=/movie/{movie_id}/download",
            status_code=303,
        )
    
    # ✅ STEP 2: ONLY INCREMENT if not requiring verification
    await increment_free_used(request)
    print(f"✅ INCREMENT DONE - User allowed to download")
    
    # Get state after increment (for debug)
    settings_after, state_after, _ = await get_user_verification_state(request)
    print(f"🔍 AFTER INCREMENT:")
    print(f"   - free_used: {state_after['free_used']}")
    
    # ✅ STEP 3: Redirect to actual download_url
    db = get_db()
    movie_doc: Optional[dict] = None
    if db is not None:
        try:
            oid = ObjectId(movie_id)
            movie_doc = await db["movies"].find_one({"_id": oid})
        except Exception:
            movie_doc = None

    if not movie_doc or not movie_doc.get("download_url"):
        return RedirectResponse(url=f"/movie/{movie_id}", status_code=303)

    print(f"✅ ALLOWING DOWNLOAD")
    print("="*60 + "\n")
    return RedirectResponse(url=movie_doc["download_url"], status_code=302)
        
