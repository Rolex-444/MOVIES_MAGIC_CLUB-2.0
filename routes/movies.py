# routes/movies.py

from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from db import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ---------- HELPERS ----------


def _movie_to_ctx(doc: dict) -> dict:
    """Normalize movie document into a template-friendly dict."""
    return {
        "id": str(doc.get("_id")),
        "title": doc.get("title", "Untitled"),
        "year": doc.get("year"),
        "language": doc.get("language"),
        "quality": doc.get("quality", "HD"),
        "category": doc.get("category"),
        "poster_path": doc.get("poster_path"),
        "watch_url": doc.get("watch_url"),
        "download_url": doc.get("download_url"),
        "languages": doc.get("languages", []),
        "description": doc.get("description", ""),
    }


# ---------- MOVIES HOME (MOVIES TAB) ----------


@router.get("/", response_class=HTMLResponse)
async def movies_home(request: Request):
    """
    Home page for Movies tab.

    Provides:
      - latest_movies: for hero + Trending + All movies
      - tamil_movies / telugu_movies / hindi_movies / malayalam_movies / kannada_movies
        based on the 'languages' array (checkbox selection).
    """
    db = get_db()

    latest_movies: List[dict] = []
    tamil_movies: List[dict] = []
    telugu_movies: List[dict] = []
    hindi_movies: List[dict] = []
    malayalam_movies: List[dict] = []
    kannada_movies: List[dict] = []

    if db is not None:
        col = db["movies"]

        # latest uploads (used in hero + trending + all movies)
        cursor = col.find().sort("_id", -1).limit(20)
        latest_movies = [_movie_to_ctx(doc) async for doc in cursor]

        # language rows: match inside languages[] array
        async def _lang_list(lang: str, limit: int = 12) -> List[dict]:
            cur = (
                col.find({"languages": lang})  # movie appears if that language was checked
                .sort("_id", -1)
                .limit(limit)
            )
            return [_movie_to_ctx(doc) async for doc in cur]

        tamil_movies = await _lang_list("Tamil")
        telugu_movies = await _lang_list("Telugu")
        hindi_movies = await _lang_list("Hindi")
        malayalam_movies = await _lang_list("Malayalam")
        kannada_movies = await _lang_list("Kannada")

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


# ---------- MOVIES BROWSE (BY GENRE OR ALL) ----------


@router.get("/movies/browse", response_class=HTMLResponse)
async def movies_browse(request: Request, genre: str = ""):
    """
    Browse page for movies.

    - /movies/browse              -> all movies
    - /movies/browse?genre=Action -> movies whose category contains 'Action'
    """
    db = get_db()
    movies_list: List[dict] = []

    if db is not None:
        col = db["movies"]
        query = {}
        if genre:
            query["category"] = {"$regex": genre, "$options": "i"}

        cursor = col.find(query).sort("_id", -1)
        movies_list = [_movie_to_ctx(doc) async for doc in cursor]

    return templates.TemplateResponse(
        "movies_browse.html",
        {
            "request": request,
            "movies_list": movies_list,
            "genre": genre,
        },
    )


# ---------- MOVIE DETAIL PAGE ----------


@router.get("/movie/{movie_id}", response_class=HTMLResponse)
async def movie_detail(request: Request, movie_id: str):
    """
    Single movie detail page.

    Template movie_detail.html expects:

      movie.poster_path
      movie.title
      movie.year
      movie.quality
      movie.language      (primary language)
      movie.category
      movie.audio         (all audio languages as a comma list)
      movie.subtitles     (optional)
      movie.is_multi_dubbed
      movie.watch_url
      movie.download_url
      movie.description
    """
    db = get_db()
    movie_doc: Optional[dict] = None

    if db is not None:
        try:
            oid = ObjectId(movie_id)
            movie_doc = await db["movies"].find_one({"_id": oid})
        except Exception:
            movie_doc = None

    if not movie_doc:
        return templates.TemplateResponse(
            "movie_detail.html",
            {"request": request, "movie": None},
        )

    # Build audio text from languages[]
    languages = movie_doc.get("languages") or []
    primary_language = movie_doc.get("language") or (languages[0] if languages else "Tamil")
    audio_text = ", ".join(languages) if languages else primary_language

    movie_ctx = {
        "id": str(movie_doc.get("_id")),
        "title": movie_doc.get("title", "Untitled"),
        "year": movie_doc.get("year"),
        "quality": movie_doc.get("quality", "HD"),
        "language": primary_language,
        "category": movie_doc.get("category", ""),
        "poster_path": movie_doc.get("poster_path"),
        "watch_url": movie_doc.get("watch_url"),
        "download_url": movie_doc.get("download_url"),
        "description": movie_doc.get("description", ""),
        # fields used in movie_detail.html
        "audio": audio_text,
        "subtitles": movie_doc.get("subtitles", ""),
        "is_multi_dubbed": len(languages) > 1,
    }

    return templates.TemplateResponse(
        "movie_detail.html",
        {"request": request, "movie": movie_ctx},
    )
    
