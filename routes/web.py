# routes/web.py

from typing import List
from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ---------- HOME + SEARCH ----------

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = get_db()
    latest_movies = []
    tamil_movies = []
    telugu_movies = []
    hindi_movies = []
    malayalam_movies = []
    kannada_movies = []

    if db is not None:
        movies_col = db["movies"]
        
        # ✅ FIX: Exclude series by filtering out documents with 'seasons' field
        cursor = movies_col.find({"seasons": {"$exists": False}}).sort("_id", -1).limit(5)
        latest_movies = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", "Untitled"),
                "year": doc.get("year"),
                "language": doc.get("language"),
                "quality": doc.get("quality", "HD"),
                "category": doc.get("category"),
                "poster_path": doc.get("poster_path"),
            }
            async for doc in cursor
        ]

        # ✅ FIX: Also exclude series in language queries
        async def fetch_by_language(lang: str, limit: int = 12):
            cur = (
                movies_col
                .find({
                    "languages": lang,
                    "seasons": {"$exists": False}  # ✅ Exclude series
                })
                .sort("_id", -1)
                .limit(limit)
            )
            return [
                {
                    "id": str(d.get("_id")),
                    "title": d.get("title", "Untitled"),
                    "year": d.get("year"),
                    "language": d.get("language"),
                    "quality": d.get("quality", "HD"),
                    "poster_path": d.get("poster_path"),
                }
                async for d in cur
            ]

        tamil_movies = await fetch_by_language("Tamil")
        telugu_movies = await fetch_by_language("Telugu")
        hindi_movies = await fetch_by_language("Hindi")
        malayalam_movies = await fetch_by_language("Malayalam")
        kannada_movies = await fetch_by_language("Kannada")

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "latest_movies": latest_movies,
            "tamil_movies": tamil_movies,
            "telugu_movies": telugu_movies,
            "hindi_movies": hindi_movies,
            "malayalam_movies": malayalam_movies,
            "kannada_movies": kannada_movies,
        },
    )


@router.get("/search", response_class=HTMLResponse)
async def search_movies(request: Request, q: str = ""):
    db = get_db()
    movies: List[dict] = []
    if db is not None and q.strip():
        # ✅ FIX: Exclude series from search results
        cursor = db["movies"].find(
            {
                "title": {"$regex": q, "$options": "i"},
                "seasons": {"$exists": False}  # ✅ Exclude series
            }
        ).limit(30)
        movies = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", ""),
                "year": doc.get("year"),
                "language": doc.get("language"),
                "quality": doc.get("quality"),
            }
            async for doc in cursor
        ]
    context = {
        "request": request,
        "query": q,
        "movies": movies,
    }
    return templates.TemplateResponse("search.html", context)

# Rest of your code stays the same...

# ---------- BROWSE PAGES (SEE ALL) ----------

LANGUAGE_MAP = {
    "tamil": "Tamil",
    "telugu": "Telugu",
    "hindi": "Hindi",
    "malayalam": "Malayalam",
    "kannada": "Kannada",
}


async def _build_movie_list(cursor):
    return [
        {
            "id": str(doc.get("_id")),
            "title": doc.get("title", "Untitled"),
            "year": doc.get("year"),
            "language": doc.get("language"),
            "quality": doc.get("quality", "HD"),
            "category": doc.get("category"),
            "poster_path": doc.get("poster_path"),
        }
        async for doc in cursor
    ]


@router.get("/language/{lang_slug}", response_class=HTMLResponse)
async def browse_by_language(request: Request, lang_slug: str):
    db = get_db()
    movies: List[dict] = []
    lang_key = lang_slug.lower()
    language = LANGUAGE_MAP.get(lang_key, lang_slug.title())

    if db is not None:
        # ✅ FIXED: Changed from "language" to "languages" to match array field
        cursor = (
            db["movies"]
            .find({"languages": language})  # Check if language exists in languages array
            .sort("_id", -1)
        )
        movies = await _build_movie_list(cursor)

    page_title = f"{language} movies"
    page_subtitle = f"All {language} movies saved in Movies Magic Club"

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "movies": movies,
        },
    )


GENRE_MAP = {
    "action": "Action",
    "comedy": "Comedy",
    "drama": "Drama",
    "horror": "Horror",
    "crime": "Crime",
    "romance": "Romance",
}


@router.get("/genre/{genre_slug}", response_class=HTMLResponse)
async def browse_by_genre(request: Request, genre_slug: str):
    db = get_db()
    movies: List[dict] = []
    key = genre_slug.lower()
    genre = GENRE_MAP.get(key, genre_slug.title())

    if db is not None:
        cursor = db["movies"].find(
            {"category": {"$regex": genre, "$options": "i"}}
        ).sort("_id", -1)
        movies = await _build_movie_list(cursor)

    page_title = f"{genre} movies"
    page_subtitle = f"All movies tagged as {genre}"

    return templates.TemplateResponse(
        "browse.html",
        {
            "request": request,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "movies": movies,
        },
    )


# ---------- MOVIE DETAIL + HEALTH ----------

@router.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: str):
    db = get_db()
    movie = None

    if db is not None:
        try:
            oid = ObjectId(movie_id)
            movie = await db["movies"].find_one({"_id": oid})
        except Exception:
            movie = None

    if movie:
        languages = movie.get("languages") or []
        audio_text = ", ".join(languages) if languages else movie.get(
            "audio", "Tamil, Telugu, Hindi"
        )

        movie_ctx = {
            "id": str(movie.get("_id")),
            "title": movie.get("title", "Sample Movie Title"),
            "year": movie.get("year", 2024),
            "language": movie.get("language", "Tamil"),
            "quality": movie.get("quality", "HD"),
            "category": movie.get("category", "Action"),
            "is_multi_dubbed": len(languages) > 1,
            "duration": movie.get("duration", "2h 20m"),
            "description": movie.get("description", ""),
            "audio": audio_text,
            "subtitles": movie.get("subtitles", "English"),
            "size": movie.get("size", "2.1 GB"),
            "views": movie.get("views", "12.4K"),
            "poster_path": movie.get("poster_path"),
            "watch_url": movie.get("watch_url", ""),
            "download_url": movie.get("download_url", ""),
        }
    else:
        movie_ctx = {
            "id": movie_id,
            "title": "Sample Movie Title",
            "year": 2024,
            "language": "Tamil",
            "quality": "HD",
            "category": "Action",
            "is_multi_dubbed": True,
            "duration": "2h 20m",
            "description": "",
            "audio": "Tamil, Telugu, Hindi",
            "subtitles": "English",
            "size": "2.1 GB",
            "views": "12.4K",
            "poster_path": None,
            "watch_url": "",
            "download_url": "",
        }

    return templates.TemplateResponse(
        "movie_detail.html",
        {"request": request, "movie": movie_ctx},
    )


@router.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK"


@router.get("/debug/movies-count", response_class=PlainTextResponse)
async def movies_count():
    db = get_db()
    if db is None:
        return "MongoDB not connected"
    count = await db["movies"].count_documents({})
    return f"Movies in DB: {count}"
        
