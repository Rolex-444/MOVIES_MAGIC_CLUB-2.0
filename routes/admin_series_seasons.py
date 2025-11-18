# routes/admin_series_seasons.py

import os
from datetime import datetime
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from bson import ObjectId

from db import get_db

templates = Jinja2Templates(directory="templates")

router = APIRouter()


def is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


@router.get("/admin/series/{series_id}/seasons", response_class=HTMLResponse)
async def admin_manage_seasons(request: Request, series_id: str, message: str = ""):
    """
    Seasons management page for one series.
    """
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)

    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "admin_series_seasons.html",
            {
                "request": request,
                "series": None,
                "seasons": [],
                "message": "MongoDB not connected",
            },
        )

    try:
        oid = ObjectId(series_id)
    except Exception:
        return templates.TemplateResponse(
            "admin_series_seasons.html",
            {
                "request": request,
                "series": None,
                "seasons": [],
                "message": "Invalid series id",
            },
        )

    series = await db["series"].find_one({"_id": oid})
    if not series:
        return templates.TemplateResponse(
            "admin_series_seasons.html",
            {
                "request": request,
                "series": None,
                "seasons": [],
                "message": "Series not found",
            },
        )

    cursor = (
        db["seasons"]
        .find({"series_id": oid})
        .sort("number", 1)
    )
    seasons = [
        {
            "id": str(doc["_id"]),
            "number": doc.get("number"),
            "title": doc.get("title", f"Season {doc.get('number')}"),
        }
        async for doc in cursor
    ]

    return templates.TemplateResponse(
        "admin_series_seasons.html",
        {
            "request": request,
            "series": series,
            "seasons": seasons,
            "message": message,
        },
    )
