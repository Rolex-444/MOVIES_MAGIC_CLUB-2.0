# routes/admin_episodes.py

from datetime import datetime
from typing import List

from bson import ObjectId

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


@router.get("/admin/seasons/{season_id}/episodes", response_class=HTMLResponse)
async def admin_list_episodes(request: Request, season_id: str, message: str = ""):
    """
    Episodes dashboard for a single season.
    """
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_series_episodes.html",
            {
                "request": request,
                "series": None,
                "season": None,
                "episodes": [],
                "message": "MongoDB not connected",
            },
        )

    try:
        soid = ObjectId(season_id)
    except Exception:
        return templates.TemplateResponse(
            "admin_series_episodes.html",
            {
                "request": request,
                "series": None,
                "season": None,
                "episodes": [],
                "message": "Invalid season id",
            },
        )

    season = await db["seasons"].find_one({"_id": soid})
    if not season:
        return templates.TemplateResponse(
            "admin_series_episodes.html",
            {
                "request": request,
                "series": None,
                "season": None,
                "episodes": [],
                "message": "Season not found",
            },
        )

    # parent series document
    series = await db["series"].find_one({"_id": season["series_id"]})

    # all episodes for this season
    cursor = db["episodes"].find({"season_id": soid}).sort("number", 1)
    episodes = [
        {
            "id": str(doc["_id"]),
            "number": doc.get("number"),
            "title": doc.get("title", f"Episode {doc.get('number')}"),
            "watch_url": doc.get("watch_url"),
            "download_url": doc.get("download_url"),
        }
        async for doc in cursor
    ]

    return templates.TemplateResponse(
        "admin_series_episodes.html",
        {
            "request": request,
            "series": series,
            "season": season,
            "episodes": episodes,
            "message": message,
        },
    )


@router.post("/admin/seasons/{season_id}/episodes")
async def admin_add_episode(
    request: Request,
    season_id: str,
    episode_number: int = Form(...),
    episode_title: str = Form(""),
    watch_link: str = Form(""),
    download_link: str = Form(""),
    description: str = Form(""),
):
    """
    Create a new episode inside a season.
    Also stores series_id so series detail page can query episodes easily.
    """
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return RedirectResponse(
            f"/admin/seasons/{season_id}/episodes?message=MongoDB+not+connected",
            status_code=303,
        )

    try:
        soid = ObjectId(season_id)
    except Exception:
        return RedirectResponse(
            f"/admin/seasons/{season_id}/episodes?message=Invalid+season+id",
            status_code=303,
        )

    season = await db["seasons"].find_one({"_id": soid})
    if not season:
        return RedirectResponse(
            f"/admin/seasons/{season_id}/episodes?message=Season+not+found",
            status_code=303,
        )

    series_id = season["series_id"]

    ep_doc = {
        "season_id": soid,
        "series_id": series_id,
        "number": episode_number,
        "title": episode_title or f"Episode {episode_number}",
        "watch_url": watch_link,
        "download_url": download_link,
        "description": description,
        "created_at": datetime.utcnow(),
    }

    await db["episodes"].insert_one(ep_doc)

    return RedirectResponse(
        f"/admin/seasons/{season_id}/episodes?message=Episode+added",
        status_code=303,
    )
    
