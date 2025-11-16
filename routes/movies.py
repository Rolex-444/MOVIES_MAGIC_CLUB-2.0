from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from db import get_db
from models import MovieCreate

router = APIRouter(
    prefix="/api/movies",
    tags=["movies"],
)


@router.post("/", summary="Create a new movie")
async def create_movie(movie: MovieCreate):
    """
    Insert one movie into MongoDB.
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="MongoDB not connected")

    data = movie.dict()
    data["created_at"] = datetime.utcnow()

    result = await db["movies"].insert_one(data)
    return {"id": str(result.inserted_id)}
    

@router.get("/", summary="List movies")
async def list_movies(limit: int = 20):
    """
    Get latest movies (basic list for now).
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="MongoDB not connected")

    cursor = db["movies"].find().sort("created_at", -1).limit(limit)

    movies: List[dict] = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        movies.append(doc)

    return movies
