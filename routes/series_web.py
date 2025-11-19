# routes/series_web.py

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

# ---------- HELPERS (old nested structure, still used by /series/.../episode/... if you want) ----------

def _find_season(series: dict, season_number: int) -> Optional[dict]:
    for s in series.get("seasons", []):
        if int(s.get("number", 0)) == season_number:
            return s
    return None

def _find_episode(season: dict, episode_number: int) -> Optional[dict]:
    for e in season.get("episodes", []):
        if int(e.get("number", 0)) == episode_number:
            return e
    return None


# ---------- SERIES HOME: HERO + GENRES + TRENDING + ALL ----------

@router.get("/series", response_class=HTMLResponse)
async def series_home(request: Request):
    """
    Series homepage: hero slider + genre chips + trending row + all-series row.
    Uses latest uploads from 'series' collection.
    """
    db = get_db()
    latest_series: List[dict] = []

    if db is not None:
        col = db["series"]
        cursor = col.find().sort("_id", -1).limit(20)
        latest_series = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", "Untitled series"),
                "year": doc.get("year"),
                "language": doc.get("language"),
                "quality": doc.get("quality", "HD"),
                "category": doc.get("category"),
                "poster_path": doc.get("poster_path"),
            }
            async for doc in cursor
        ]

    return templates.TemplateResponse(
        "series_index.html",
        {
            "request": request,
            "latest_series": latest_series,
            "active_genre": "",
        },
    )


# ---------- GENRE / BROWSE PAGE ----------

@router.get("/series/browse", response_class=HTMLResponse)
async def series_browse(request: Request, genre: str = ""):
    """
    Dedicated page to browse all series, optionally filtered by ?genre=.
    Matches against 'category' text (case-insensitive).
    """
    db = get_db()
    series_list: List[dict] = []

    if db is not None:
        col = db["series"]
        query = {}
        if genre:
            query["category"] = {"$regex": genre, "$options": "i"}

        cursor = col.find(query).sort("_id", -1)
        series_list = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", "Untitled series"),
                "year": doc.get("year"),
                "language": doc.get("language"),
                "quality": doc.get("quality", "HD"),
                "category": doc.get("category"),
                "poster_path": doc.get("poster_path"),
            }
            async for doc in cursor
        ]

    return templates.TemplateResponse(
        "series_browse.html",
        {
            "request": request,
            "series_list": series_list,
            "genre": genre,
        },
    )


# ---------- SERIES DETAIL: SEASONS + EPISODE SELECTOR ----------

@router.get("/series/{series_id}", response_class=HTMLResponse)
async def series_detail(request: Request, series_id: str):
    """
    Series detail page.
    - Shows series meta (title/year/language/description).
    - Lists seasons, each with its episodes.
    - User picks an episode; we send them to /episode/{episode_id}.
    """
    db = get_db()
    series = None
    seasons: List[dict] = []
    total_episodes = 0

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series = await db["series"].find_one({"_id": oid})
        except Exception:
            series = None

    if series:
        # fetch seasons for this series
        seasons_cursor = (
            db["seasons"]
            .find({"series_id": series["_id"]})
            .sort("number", 1)
        )

        async for s in seasons_cursor:
            soid = s["_id"]
            eps_cursor = (
                db["episodes"]
                .find({ "season_id": soid })
                .sort("number", 1)
            )
            eps = [
                {
                    "id": str(e["_id"]),
                    "number": e.get("number"),
                    "title": e.get("title", f"Episode {e.get('number')}"),
                }
                async for e in eps_cursor
            ]
            total_episodes += len(eps)
            seasons.append(
                {
                    "id": str(soid),
                    "number": s.get("number"),
                    "title": s.get("title", f"Season {s.get('number')}"),
                    "year": s.get("year"),
                    "episodes": eps,
                }
            )

    ctx = {
        "request": request,
        "series": series,
        "seasons": seasons,
        "episodes_count": total_episodes,
    }
    return templates.TemplateResponse("series_detail.html", ctx)


# ---------- EPISODE DETAIL BY EPISODE ID (NEW FLOW) ----------

@router.get("/episode/{episode_id}", response_class=HTMLResponse)
async def episode_detail_page(request: Request, episode_id: str):
    """
    Episode detail page for the new DB structure:
    episode -> seasons collection -> series collection.
    """
    db = get_db()
    episode_doc = None
    series = None
    season = None
    episode_ctx = None

    if db is not None:
        try:
            eid = ObjectId(episode_id)
            episode_doc = await db["episodes"].find_one({"_id": eid})
        except Exception:
            episode_doc = None

    if episode_doc:
        series = await db["series"].find_one({"_id": episode_doc["series_id"]})
        season = await db["seasons"].find_one({"_id": episode_doc["season_id"]})

        episode_ctx = {
            "id": str(episode_doc["_id"]),
            "number": episode_doc.get("number"),
            "title": episode_doc.get("title", f"Episode {episode_doc.get('number')}"),
            "description": episode_doc.get("description", ""),
            "watch_url": episode_doc.get("watch_url", ""),
            "download_url": episode_doc.get("download_url", ""),
        }

    return templates.TemplateResponse(
        "episode_detail.html",
        {
            "request": request,
            "series": series,
            "season": season,
            "episode": episode_ctx,
        },
    )


# ---------- EPISODE WATCH/DOWNLOAD GATES (WITH VERIFICATION) ----------

@router.get("/episode/{episode_id}/watch")
async def episode_watch(request: Request, episode_id: str):
    """
    Gate for episode Watch button.
    Uses same verification + counter as movies.
    """
    # 1) Check if verification required
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/episode/{episode_id}/watch",
            status_code=303,
        )

    # 2) Passed → count this click
    await increment_free_used(request)

    # 3) Redirect to actual watch_url
    db = get_db()
    episode_doc: Optional[dict] = None
    if db is not None:
        try:
            eid = ObjectId(episode_id)
            episode_doc = await db["episodes"].find_one({"_id": eid})
        except Exception:
            episode_doc = None

    if not episode_doc or not episode_doc.get("watch_url"):
        return RedirectResponse(url=f"/episode/{episode_id}", status_code=303)

    return RedirectResponse(url=episode_doc["watch_url"], status_code=302)


@router.get("/episode/{episode_id}/download")
async def episode_download(request: Request, episode_id: str):
    """
    Gate for episode Download button.
    Uses same verification + counter as movies.
    """
    # 1) Check if verification required
    if await should_require_verification(request):
        return RedirectResponse(
            url=f"/verify/start?next=/episode/{episode_id}/download",
            status_code=303,
        )

    # 2) Passed → count this click
    await increment_free_used(request)

    # 3) Redirect to actual download_url
    db = get_db()
    episode_doc: Optional[dict] = None
    if db is not None:
        try:
            eid = ObjectId(episode_id)
            episode_doc = await db["episodes"].find_one({"_id": eid})
        except Exception:
            episode_doc = None

    if not episode_doc or not episode_doc.get("download_url"):
        return RedirectResponse(url=f"/episode/{episode_id}", status_code=303)

    return RedirectResponse(url=episode_doc["download_url"], status_code=302)


# ---------- OLD NESTED EPISODE ROUTE (optional legacy) ----------

@router.get(
    "/series/{series_id}/season/{season_number}/episode/{episode_number}",
    response_class=HTMLResponse,
)
async def episode_detail(
    request: Request,
    series_id: str,
    season_number: int,
    episode_number: int,
):
    """
    Legacy route, only used if series document embeds seasons/episodes.
    Keeps your old /series/.../season/.../episode/... URLs working.
    """
    db = get_db()
    series_doc = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series_doc = await db["series"].find_one({"_id": oid})
        except Exception:
            series_doc = None

    if not series_doc:
        return templates.TemplateResponse(
            "episode_detail.html",
            {"request": request, "series": None, "season": None, "episode": None},
        )

    season = _find_season(series_doc, season_number)
    episode = _find_episode(season or {}, episode_number) if season else None

    if not (season and episode):
        return templates.TemplateResponse(
            "episode_detail.html",
            {"request": request, "series": None, "season": None, "episode": None},
        )

    languages = series_doc.get("languages") or []
    audio_text = ", ".join(languages) if languages else series_doc.get("language", "Tamil")

    series_ctx = {
        "id": str(series_doc.get("_id")),
        "title": series_doc.get("title", "Untitled series"),
        "language": series_doc.get("language", "Tamil"),
        "category": series_doc.get("category", ""),
        "poster_path": series_doc.get("poster_path"),
        "audio": audio_text,
        "languages": languages,
    }

    episode_ctx = {
        # legacy embedded episodes usually don't have an _id → no gated URL
        "id": None,
        "number": episode.get("number"),
        "title": episode.get("title", ""),
        "description": episode.get("description", ""),
        "watch_url": episode.get("watch_url", ""),
        "download_url": episode.get("download_url", ""),
    }

    season_ctx = {
        "number": season.get("number"),
        "name": season.get("name", f"Season {season.get('number')}"),
        "year": season.get("year"),
    }

    return templates.TemplateResponse(
        "episode_detail.html",
        {
            "request": request,
            "series": series_ctx,
            "season": season_ctx,
            "episode": episode_ctx,
        },
    )
    
