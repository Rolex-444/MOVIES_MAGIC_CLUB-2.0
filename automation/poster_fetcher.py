"""
TMDb Poster & Metadata Fetcher
"""
import httpx
from typing import Optional, Dict
from .config import TMDB_API_KEY, TMDB_API_URL


class PosterFetcher:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        self.api_url = TMDB_API_URL
        self.image_base_url = "https://image.tmdb.org/t/p/w500"
    
    async def search_movie(self, title: str, year: Optional[int] = None) -> Optional[Dict]:
        """
        Search TMDb for movie
        Returns: movie details with poster URL
        """
        try:
            params = {
                "api_key": self.api_key,
                "query": title,
                "language": "en-US"
            }
            
            if year:
                params["year"] = year
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.api_url}/search/movie",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    
                    if results:
                        movie = results[0]  # Get first result
                        return {
                            "title": movie.get("title"),
                            "year": movie.get("release_date", "")[:4],
                            "poster_url": f"{self.image_base_url}{movie.get('poster_path')}" if movie.get('poster_path') else None,
                            "backdrop_url": f"{self.image_base_url}{movie.get('backdrop_path')}" if movie.get('backdrop_path') else None,
                            "overview": movie.get("overview"),
                            "rating": movie.get("vote_average"),
                            "genres": movie.get("genre_ids", [])
                        }
        
        except Exception as e:
            print(f"❌ TMDb search error: {e}")
        
        return None
    
    async def download_poster(self, poster_url: str) -> Optional[bytes]:
        """Download poster image as bytes"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(poster_url)
                
                if response.status_code == 200:
                    return response.content
        
        except Exception as e:
            print(f"❌ Poster download error: {e}")
        
        return None
