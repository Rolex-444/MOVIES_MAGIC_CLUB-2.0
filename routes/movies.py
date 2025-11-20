# routes/movies.py

from typing import Optional, List
from bson import ObjectId
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
import random

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def _prepare_movie_for_template(doc: dict) -> Optional[dict]:
    """Convert MongoDB movie doc to template-friendly format"""
    if not doc or "_id" not in doc:
        return None
    
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", "Untitled"),
        "year": doc.get("year"),
        "language": doc.get("language"),
        "languages": doc.get("languages", []),
        "quality": doc.get("quality", "HD"),
        "category": doc.get("category"),
        "poster_path": doc.get("poster_path"),
        "watch_url": doc.get("watch_url"),
        "download_url": doc.get("download_url"),
        "qualities": doc.get("qualities", {}),  # ⭐ FIX: Add quality links
        "description": doc.get("description", ""),
        "is_multi_dubbed": doc.get("is_multi_dubbed", False),
        "created_at": doc.get("created_at"),
    }

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "movies": [], "trending_movies": [], "recent_movies": []},
        )

    # Get all movies
    movies_cursor = db["movies"].find().sort("created_at", -1)
    raw_movies = await movies_cursor.to_list(length=50)
    
    # Convert to template format (filter out None values)
    movies = [_prepare_movie_for_template(m) for m in raw_movies if _prepare_movie_for_template(m)]

    # Prepare trending (random sample) and recent
    trending_movies = random.sample(movies, min(8, len(movies))) if movies else []
    recent_movies = movies[:12]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "movies": movies,
            "trending_movies": trending_movies,
            "recent_movies": recent_movies,
        },
    )

@router.get("/movies", response_class=HTMLResponse)
async def movies_page(
    request: Request,
    language: str = Query(None),
    quality: str = Query(None),
    category: str = Query(None),
    q: str = Query(None),
):
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "movies.html",
            {
                "request": request,
                "movies": [],
                "selected_language": language,
                "selected_quality": quality,
                "selected_category": category,
                "query": q,
            },
        )

    query = {}
    if language:
        query["language"] = language
    if quality:
        query["quality"] = {"$regex": quality, "$options": "i"}
    if category:
        query["category"] = {"$regex": category, "$options": "i"}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]

    movies_cursor = db["movies"].find(query).sort("created_at", -1)
    raw_movies = await movies_cursor.to_list(length=100)
    
    # Convert to template format (filter out None values)
    movies = [_prepare_movie_for_template(m) for m in raw_movies if _prepare_movie_for_template(m)]

    return templates.TemplateResponse(
        "movies.html",
        {
            "request": request,
            "movies": movies,
            "selected_language": language,
            "selected_quality": quality,
            "selected_category": category,
            "query": q,
        },
    )

@router.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: str):
    db = get_db()
    if db is None:
        return templates.TemplateResponse(
            "movie_detail.html",
            {"request": request, "movie": None, "error": "Database not connected"},
        )

    # Validate movie_id format
    if not movie_id or len(movie_id) != 24:
        return templates.TemplateResponse(
            "movie_detail.html",
            {"request": request, "movie": None, "error": "Invalid movie ID format"},
        )

    try:
        movie_doc = await db["movies"].find_one({"_id": ObjectId(movie_id)})
    except Exception as e:
        return templates.TemplateResponse(
            "movie_detail.html",
            {"request": request, "movie": None, "error": f"Error finding movie: {e}"},
        )

    if not movie_doc:
        return templates.TemplateResponse(
            "movie_detail.html",
            {"request": request, "movie": None, "error": "Movie not found in database"},
        )

    # Convert to template format
    movie = _prepare_movie_for_template(movie_doc)

    # Get related movies (handle errors gracefully)
    try:
        related_query = {
            "$and": [
                {"_id": {"$ne": ObjectId(movie_id)}},
                {
                    "$or": [
                        {"language": movie_doc.get("language")},
                        {"category": movie_doc.get("category")},
                    ]
                },
            ]
        }
        related_cursor = db["movies"].find(related_query).limit(8)
        raw_related = await related_cursor.to_list(length=8)
        related_movies = [_prepare_movie_for_template(m) for m in raw_related if _prepare_movie_for_template(m)]
    except:
        related_movies = []

    return templates.TemplateResponse(
        "movie_detail.html",
        {
            "request": request,
            "movie": movie,
            "related_movies": related_movies,
        },
        )
    
