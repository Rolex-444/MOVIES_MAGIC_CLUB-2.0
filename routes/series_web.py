# routes/series_web.py

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------- HELPERS ----------


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


# ---------- SERIES DETAIL (SEASONS + EPISODES) ----------

@router.get("/series/{series_id}", response_class=HTMLResponse)
async def series_detail(request: Request, series_id: str):
    db = get_db()
    series = None
    episodes = []
    primary_episode = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series = await db["series"].find_one({"_id": oid})
        except Exception:
            series = None

        if series:
            # all episodes for this series (across seasons)
            cur = (
                db["episodes"]
                .find({"series_id": series["_id"]})
                .sort([("season_id", 1), ("number", 1)])
            )
            episodes = [
                {
                    "id": str(doc["_id"]),
                    "number": doc.get("number"),
                    "title": doc.get("title", f"Episode {doc.get('number')}"),
                    "watch_url": doc.get("watch_url"),
                    "download_url": doc.get("download_url"),
                }
                async for doc in cur
            ]
            if episodes:
                primary_episode = episodes[0]

    ctx = {
        "request": request,
        "series": series,
        "episodes": episodes,
        "episodes_count": len(episodes),
        "primary_episode": primary_episode,
    }
    return templates.TemplateResponse("series_detail.html", ctx)
    


# ---------- EPISODE DETAIL (WATCH / DOWNLOAD) ----------


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
    Single episode page: uses series poster + meta, and shows
    Watch / Download buttons for that episode.

    Multi-audio:
      - admin stores languages[] in series document
      - primary language is series.language
      - here we build series.audio string from languages[]
    """
    db = get_db()
    series = None

    if db is not None:
        try:
            oid = ObjectId(series_id)
            series = await db["series"].find_one({"_id": oid})
        except Exception:
            series = None

    if not series:
        return templates.TemplateResponse(
            "episode_detail.html",
            {"request": request, "series": None, "season": None, "episode": None},
        )

    season = _find_season(series, season_number)
    episode = _find_episode(season or {}, episode_number) if season else None

    if not (season and episode):
        return templates.TemplateResponse(
            "episode_detail.html",
            {"request": request, "series": None, "season": None, "episode": None},
        )

    # multi-audio text from languages[]
    languages = series.get("languages") or []
    audio_text = ", ".join(languages) if languages else series.get("language", "Tamil")

    series_ctx = {
        "id": str(series.get("_id")),
        "title": series.get("title", "Untitled series"),
        "language": series.get("language", "Tamil"),  # primary UI language
        "category": series.get("category", ""),
        "poster_path": series.get("poster_path"),
        "audio": audio_text,
        "languages": languages,
    }

    episode_ctx = {
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
    
