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
                "languages": doc.get("languages", []),  # ✅ ADDED
                "quality": doc.get("quality", "HD"),
                "category": doc.get("category"),
                "poster_path": doc.get("poster_path"),
            }
            async for doc in cursor
        ]

        # ✅ FIXED: Changed from "language" to "languages"
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
                    "languages": d.get("languages", []),  # ✅ ADDED
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
        # ✅ FIX: Exclude series from search
        cursor = db["movies"].find(
            {
                "title": {"$regex": q, "$options": "i"},
                "seasons": {"$exists": False}
            }
        ).limit(30)
        movies = [
            {
                "id": str(doc.get("_id")),
                "title": doc.get("title", ""),
                "year": doc.get("year"),
                "language": doc.get("language"),
                "languages": doc.get("languages", []),  # ✅ ADDED
                "quality": doc.get("quality"),
                "poster_path": doc.get("poster_path"),

            }
            async for doc in cursor
        ]
    context = {
        "request": request,
        "query": q,
        "movies": movies,
    }
    return templates.TemplateResponse("search.html", context)


@router.get("/legal", response_class=HTMLResponse)
async def legal_page(request: Request):
    return templates.TemplateResponse(
        "legal.html",
        {"request": request},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return """User-agent: *
Disallow: /admin/
Allow: /"""


# ---------- LANGUAGE & GENRE MAP ----------

LANGUAGE_MAP = {
    "tamil": "Tamil",
    "telugu": "Telugu",
    "hindi": "Hindi",
    "malayalam": "Malayalam",
    "kannada": "Kannada",
    "english": "English",
}

GENRE_MAP = {
    "action": "Action",
    "comedy": "Comedy",
    "drama": "Drama",
    "horror": "Horror",
    "romance": "Romance",
    "thriller": "Thriller",
    "sci-fi": "Sci-Fi",
    "fantasy": "Fantasy",
}


# ---------- BROWSE BY LANGUAGE ----------

@router.get("/language/{lang_slug}", response_class=HTMLResponse)
async def browse_by_language(request: Request, lang_slug: str):
    db = get_db()
    movies: List[dict] = []
    lang_key = lang_slug.lower()
    language = LANGUAGE_MAP.get(lang_key, lang_slug.title())

    if db is not None:
        cursor = (
            db["movies"]
            .find({
                "languages": language,
                "seasons": {"$exists": False}  # ✅ FIX: Exclude series
            })
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


# ---------- BROWSE BY GENRE ----------

@router.get("/genre/{genre_slug}", response_class=HTMLResponse)
async def browse_by_genre(request: Request, genre_slug: str):
    db = get_db()
    movies: List[dict] = []
    key = genre_slug.lower()
    genre = GENRE_MAP.get(key, genre_slug.title())

    if db is not None:
        cursor = db["movies"].find(
            {
                "category": {"$regex": genre, "$options": "i"},
                "seasons": {"$exists": False}  # ✅ FIX: Exclude series
            }
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


# ---------- HELPER FUNCTIONS ----------

async def _build_movie_list(cursor) -> List[dict]:
    """Convert async cursor to list of movie dicts"""
    return [
        {
            "id": str(doc.get("_id")),
            "title": doc.get("title", "Untitled"),
            "year": doc.get("year"),
            "language": doc.get("language"),
            "languages": doc.get("languages", []),  # ✅ ADDED - Multi-Audio support!
            "quality": doc.get("quality", "HD"),
            "category": doc.get("category"),
            "poster_path": doc.get("poster_path"),
        }
        async for doc in cursor
    ]
