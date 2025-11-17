# routes/series_web.py

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime

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


def _get_session_id(request: Request) -> str:
    """Ensure there is a stable session_id for this browser."""
    sid = request.session.get("session_id")
    if not sid:
        import uuid

        sid = uuid.uuid4().hex
        request.session["session_id"] = sid
    return sid


# ---------- SERIES HOME: HERO + GENRES + TRENDING + CONTINUE ----------


@router.get("/series", response_class=HTMLResponse)
async def series_home(request: Request):
    """
    Series homepage: latest hero + genres + trending + continue watching.

    - latest_series: latest uploads (for hero + trending)
    - continue_items: last watched episodes from this session
    """
    db = get_db()

    latest_series: List[dict] = []
    continue_items: List[dict] = []

    if db is not None:
        col = db["series"]

        # Latest 12 series for hero + trending + continue placeholder
        cursor = col.find().sort("_id", -1).limit(12)
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

        # Real continue watching from progress collection
        session_id = _get_session_id(request)
        prog_col = db["series_progress"]
        prog_cursor = (
            prog_col.find({"session_id": session_id})
            .sort("updated_at", -1)
            .limit(10)
        )

        progress_list = [p async for p in prog_cursor]

        # Join progress entries with series documents
        for p in progress_list:
            try:
                sid = ObjectId(p["series_id"])
                sdoc = await col.find_one({"_id": sid})
            except Exception:
                sdoc = None

            if not sdoc:
                continue

            continue_items.append(
                {
                    "series_id": p["series_id"],
                    "title": sdoc.get("title", "Untitled series"),
                    "poster_path": sdoc.get("poster_path"),
                    "season_number": p.get("season_number"),
                    "episode_number": p.get("episode_number"),
                    "updated_at": p.get("updated_at"),
                }
            )

    return templates.TemplateResponse(
        "series_index.html",
        {
            "request": request,
            "latest_series": latest_series,
            "active_genre": "",
            "continue_items": continue_items,
        },
    )


# ---------- GENRE / BROWSE PAGE ----------


@router.get("/series/browse", response_class=HTMLResponse)
async def series_browse(request: Request, genre: str = ""):
    """
    Dedicated page to browse all series, optionally filtered by ?genre=.
    Uses category field for matching.
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
async def series_detail(
    request: Request,
    series_id: str,
    season: int = 1,
):
    """
    Series detail page with seasons + episodes.
    ?season=N chooses which season to show; default 1.
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
            "series_detail.html",
            {
                "request": request,
                "series": None,
                "selected_season": None,
                "episodes": [],
            },
        )

    seasons = series.get("seasons", [])
    if not seasons:
        selected_season = None
        episodes = []
    else:
        selected_season = _find_season(series, season) or seasons[0]
        episodes = selected_season.get("episodes", [])

    series_ctx = {
        "id": str(series.get("_id")),
        "title": series.get("title", "Untitled series"),
        "language": series.get("language", "Tamil"),
        "category": series.get("category", ""),
        "description": series.get("description", ""),
        "poster_path": series.get("poster_path"),
        "seasons": seasons,
    }

    return templates.TemplateResponse(
        "series_detail.html",
        {
            "request": request,
            "series": series_ctx,
            "selected_season": selected_season,
            "episodes": episodes,
        },
    )


# ---------- EPISODE DETAIL (WATCH / DOWNLOAD + PROGRESS) ----------


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
    Single episode page:

    - Uses series poster + meta
    - Shows Watch / Download
    - Records 'continue watching' entry per session
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

    # ----- record progress for Continue watching -----
    if db is not None:
        session_id = _get_session_id(request)
        prog_col = db["series_progress"]
        await prog_col.update_one(
            {
                "session_id": session_id,
                "series_id": str(series.get("_id")),
            },
            {
                "$set": {
                    "season_number": int(season_number),
                    "episode_number": int(episode_number),
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

    return templates.TemplateResponse(
        "episode_detail.html",
        {
            "request": request,
            "series": series_ctx,
            "season": season_ctx,
            "episode": episode_ctx,
        },
)
