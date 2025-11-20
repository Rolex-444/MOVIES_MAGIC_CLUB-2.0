# routes/quality.py
"""
Quality selection system for movies
- Smart single/multiple quality detection
- Separate file - no modification to existing routes
- Verification already handled in movies.py - we don't touch it
"""

from typing import Dict, Optional
from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Quality metadata configuration
QUALITIES = {
    "480p": {
        "label": "480p",
        "description": "Standard Definition",
        "color": "#06b6d4",
        "icon": "💧",
        "order": 1
    },
    "720p": {
        "label": "720p",
        "description": "High Definition",
        "color": "#22c55e",
        "icon": "✨",
        "order": 2
    },
    "1080p": {
        "label": "1080p",
        "description": "Full HD",
        "color": "#f97316",
        "icon": "🔥",
        "order": 3
    },
    "2k": {
        "label": "2K",
        "description": "Quad HD (1440p)",
        "color": "#a855f7",
        "icon": "💎",
        "order": 4
    },
    "4k": {
        "label": "4K",
        "description": "Ultra HD (2160p)",
        "color": "#ef4444",
        "icon": "👑",
        "order": 5
    }
}


def get_available_qualities(content_doc: dict) -> Dict:
    """
    Extract available qualities from movie document.
    Returns: {quality_name: {watch_url, download_url, metadata}}
    """
    qualities_data = content_doc.get("qualities", {})
    available = {}
    
    for quality_name, links in qualities_data.items():
        # Only include if at least one URL exists
        if links.get("watch_url") or links.get("download_url"):
            # Get metadata or use defaults
            metadata = QUALITIES.get(quality_name, {
                "label": quality_name,
                "description": "Quality",
                "color": "#64748b",
                "icon": "🎬",
                "order": 99
            })
            
            # Merge links with metadata
            available[quality_name] = {
                "watch_url": links.get("watch_url"),
                "download_url": links.get("download_url"),
                **metadata
            }
    
    # Sort by order
    return dict(sorted(available.items(), key=lambda x: x[1].get("order", 99)))


@router.get("/movie/{movie_id}/quality", response_class=HTMLResponse)
async def movie_quality_selector(request: Request, movie_id: str):
    """
    Quality selector page - Visual Design Mockup style
    Shows only when multiple qualities available
    """
    db = get_db()
    if not db:
        return RedirectResponse(url="/", status_code=303)
    
    try:
        movie_doc = await db["movies"].find_one({"_id": ObjectId(movie_id)})
    except:
        return RedirectResponse(url="/", status_code=303)
    
    if not movie_doc:
        return RedirectResponse(url="/", status_code=303)
    
    available_qualities = get_available_qualities(movie_doc)
    
    # If no qualities, redirect back to movie detail
    if not available_qualities:
        return RedirectResponse(url=f"/movie/{movie_id}", status_code=303)
    
    return templates.TemplateResponse(
        "quality_selector.html",
        {
            "request": request,
            "qualities": available_qualities,
            "movie_title": movie_doc.get("title", "Movie"),
            "movie_year": movie_doc.get("year"),
            "movie_id": movie_id,
            "content_type": "movie",
        },
    )
