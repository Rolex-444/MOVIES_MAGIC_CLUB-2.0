"""
TamilMV Scraper with Smart File Selection
"""
import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from .config import TAMILMV_BASE_URL, SELECTION_RULES


class TamilMVScraper:
    def __init__(self):
        self.base_url = TAMILMV_BASE_URL
        self.selection_rules = SELECTION_RULES
    
    async def get_latest_movies(self, limit: int = 20) -> List[Dict]:
        """
        Scrape latest movies from TamilMV
        Returns list of movie dicts with title, year, torrents
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{self.base_url}/index.php?/forums/forum/8-tamil-dubbed-movies/")
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                movies = []
                
                # Find all movie topics
                topics = soup.find_all('li', class_='ipsDataItem')[:limit]
                
                for topic in topics:
                    movie_data = await self._parse_topic(topic)
                    if movie_data:
                        movies.append(movie_data)
                
                return movies
        
        except Exception as e:
            print(f"❌ TamilMV scrape error: {e}")
            return []
    
    async def _parse_topic(self, topic) -> Optional[Dict]:
        """Parse individual movie topic"""
        try:
            # Get movie title and link
            title_elem = topic.find('a', class_='ipsDataItem_title')
            if not title_elem:
                return None
            
            title = title_elem.text.strip()
            topic_url = title_elem['href']
            
            # Extract year from title (e.g., "Amaran (2024)")
            year_match = re.search(r'\((\d{4})\)', title)
            year = int(year_match.group(1)) if year_match else None
            
            # Clean title (remove year and extra info)
            clean_title = re.sub(r'\(\d{4}\)', '', title).strip()
            clean_title = re.split(r'[-–]', clean_title)[0].strip()
            
            return {
                "title": clean_title,
                "raw_title": title,
                "year": year,
                "topic_url": topic_url
            }
        
        except Exception as e:
            print(f"⚠️ Parse topic error: {e}")
            return None
    
    async def get_torrent_links(self, topic_url: str) -> List[Dict]:
        """
        Get all torrent/magnet links from a movie page
        Returns list with title, size, magnet link
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(topic_url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                torrents = []
                
                # Find magnet links
                magnet_links = soup.find_all('a', href=re.compile(r'^magnet:\?'))
                
                for link in magnet_links:
                    magnet = link['href']
                    
                    # Try to find size info nearby
                    parent_text = link.parent.get_text()
                    size_gb = self._extract_size(parent_text)
                    
                    # Get quality from title/text
                    quality_text = link.get_text() or parent_text
                    
                    torrents.append({
                        "title": quality_text.strip(),
                        "magnet": magnet,
                        "size_gb": size_gb
                    })
                
                return torrents
        
        except Exception as e:
            print(f"❌ Get torrents error: {e}")
            return []
    
    def _extract_size(self, text: str) -> float:
        """Extract file size in GB from text"""
        try:
            # Match patterns like "2.1GB", "2.1 GB", "2100MB"
            size_match = re.search(r'(\d+\.?\d*)\s*(GB|MB)', text, re.IGNORECASE)
            if size_match:
                size = float(size_match.group(1))
                unit = size_match.group(2).upper()
                
                if unit == 'MB':
                    size = size / 1024  # Convert MB to GB
                
                return round(size, 2)
        except:
            pass
        
        return 0.0
    
    def select_best_torrent(self, torrents: List[Dict]) -> Optional[Dict]:
        """
        Smart selection: 1080p 1-3GB → Any 1080p → 720p HQ
        """
        if not torrents:
            return None
        
        blacklist = self.selection_rules['blacklist']
        
        # Filter out blacklisted files
        valid_torrents = [
            t for t in torrents
            if not any(kw in t['title'] for kw in blacklist)
        ]
        
        if not valid_torrents:
            return None
        
        # Category 1: OPTIMAL (1080p + 1-3GB)
        optimal = self.selection_rules['optimal']
        optimal_files = [
            t for t in valid_torrents
            if '1080p' in t['title']
            and optimal['min_size_gb'] <= t['size_gb'] <= optimal['max_size_gb']
        ]
        
        if optimal_files:
            # Pick smallest in optimal range
            return min(optimal_files, key=lambda x: x['size_gb'])
        
        # Category 2: FALLBACK 1080p (any size)
        fallback_1080p = self.selection_rules['fallback_1080p']
        fallback_files = [
            t for t in valid_torrents
            if '1080p' in t['title']
            and fallback_1080p['min_size_gb'] <= t['size_gb'] <= fallback_1080p['max_size_gb']
        ]
        
        if fallback_files:
            # Pick smallest 1080p
            return min(fallback_files, key=lambda x: x['size_gb'])
        
        # Category 3: LAST RESORT (720p HQ)
        fallback_720p = self.selection_rules['fallback_720p']
        last_resort = [
            t for t in valid_torrents
            if '720p' in t['title']
            and 'HQ' in t['title']
            and fallback_720p['min_size_gb'] <= t['size_gb'] <= fallback_720p['max_size_gb']
        ]
        
        if last_resort:
            return min(last_resort, key=lambda x: x['size_gb'])
        
        # Nothing acceptable found
        return None
