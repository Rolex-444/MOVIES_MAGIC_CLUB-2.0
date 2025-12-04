"""
Automation Configuration
Add your API keys here as environment variables
"""
import os

# ========== DEBRID SERVICE SETTINGS ==========
# Get free API key from: https://debrid-link.com/
DEBRID_API_KEY = os.getenv("DEBRID_API_KEY", "")
DEBRID_API_URL = "https://debrid-link.com/api/v2"

# ========== PPD/PPV WEBSITE SETTINGS ==========
# Your PPD site API credentials
PPD_API_KEY = os.getenv("PPD_API_KEY", "")
PPD_API_URL = os.getenv("PPD_API_URL", "")  # e.g., https://krakenfiles.com/api

# ========== TMDB SETTINGS (Free API) ==========
# Get free key from: https://www.themoviedb.org/settings/api
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_API_URL = "https://api.themoviedb.org/3"

# ========== TAMILMV SCRAPER SETTINGS ==========
TAMILMV_BASE_URL = "https://tamilmv.re"
TAMILMV_LATEST_URL = f"{TAMILMV_BASE_URL}/index.php?/forums/forum/8-tamil-dubbed-movies/"

# ========== FILE SELECTION RULES ==========
SELECTION_RULES = {
    # Priority 1: Optimal Range (1-3GB, 1080p)
    "optimal": {
        "quality": "1080p",
        "min_size_gb": 1.0,
        "max_size_gb": 3.0,
        "priority": 1
    },
    
    # Priority 2: Fallback (Any 1080p, even if large)
    "fallback_1080p": {
        "quality": "1080p",
        "min_size_gb": 0.5,
        "max_size_gb": 15.0,  # Max 15GB
        "priority": 2
    },
    
    # Priority 3: Last Resort (720p HQ only)
    "fallback_720p": {
        "quality": "720p",
        "min_size_gb": 1.0,
        "max_size_gb": 5.0,
        "require_keywords": ["HQ"],
        "priority": 3
    },
    
    # Always skip these keywords
    "blacklist": ["CAM", "TC", "Telesync", "480p", "4K", "2160p", "HDCAM"],
    
    # Prefer these sources
    "prefer": ["WEB-DL", "BluRay", "HQ.HDRip", "WEBRip"]
}

# ========== AUTOMATION SETTINGS ==========
AUTO_RETRY_FAILED = True  # Retry failed movies after 24 hours
AUTO_NOTIFY_ADMIN = True  # Send Telegram notifications to admin
MAX_CONCURRENT_DOWNLOADS = 2  # Max parallel debrid downloads
SCRAPE_INTERVAL_MINUTES = 30  # How often to check TamilMV

# ========== TELEGRAM NOTIFICATION ==========
# Admin user ID to send notifications (optional)
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "")
