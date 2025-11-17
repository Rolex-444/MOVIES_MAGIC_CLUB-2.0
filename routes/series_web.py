# routes/series_web.py

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------- SERIES HOME (LIKE MOVIE HOME) ----------


@router.get("/series", response_class=HTMLResponse)
async def series_home(request: Request):
    """
    Series homepage: hero slider + language rows (Tamil/Telugu etc).
    Uses 'series' collection in MongoDB.
    """
    db = get_db()

    latest_series: List[dict] = []
    tamil_series: List[dict] = []
    telugu_series: List[dict] = []
    hindi_series: List[dict] = []
    malayalam_series: List[dict] = []
    kannada_series: List[dict] = []

    if db is not None:
        series_col = db["series"]

        # Latest 5 series for hero
        cursor = series_col.find().sort("_id", -1).limit(5)
        latest_series = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", "Untitled series"),
                "year": doc.get("year"),  # optional
                "language": doc.get("language"),
                "quality": doc.get("quality", "HD"),
                "category": doc.get("category"),
                "poster_path": doc.get("poster_path"),
            }
            async for doc in cursor
        ]

        async def fetch_by_language(lang: str, limit: int = 12):
            cur = (
                series_col
                .find({"language": lang})
                .sort("_id", -1)
                .limit(limit)
            )
            return [
                {
                    "id": str(d.get("_id")),
                    "title": d.get("title", "Untitled series"),
                    "year": d.get("year"),
                    "language": d.get("language"),
                    "quality": d.get("quality", "HD"),
                    "poster_path": d.get("poster_path"),
                }
                async for d in cur
            ]

        tamil_series = await fetch_by_language("Tamil")
        telugu_series = await fetch_by_language("Telugu")
        hindi_series = await fetch_by_language("Hindi")
        malayalam_series = await fetch_by_language("Malayalam")
        kannada_series = await fetch_by_language("Kannada")

    return templates.TemplateResponse(
        "series_index.html",
        {
            "request": request,
            "latest_series": latest_series,
            "tamil_series": tamil_series,
            "telugu_series": telugu_series,
            "hindi_series": hindi_series,
            "malayalam_series": malayalam_series,
            "kannada_series": kannada_series,
        },
    )


# ---------- SERIES DETAIL (SEASONS + EPISODES) ----------


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
        # simple 404-like message
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
        # pick requested season or first
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

    series_ctx = {
        "id": str(series.get("_id")),
        "title": series.get("title", "Untitled series"),
        "language": series.get("language", "Tamil"),
        "category": series.get("category", ""),
        "poster_path": series.get("poster_path"),
    }

    episode_ctx = {
        "number": episode.get("number"),
        "title": episode.get("title", ""),
        "description": episode.get("description", ""),
        "duration": episode.get("duration", ""),
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
