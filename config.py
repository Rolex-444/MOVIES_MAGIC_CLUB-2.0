import os

# Telegram Bot credentials from environment variables
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Channel ID (full id from Pyrogram, negative, like -1003316755829)
CHANNEL_ID = -1003467686120  # <-- unga actual id here

# Verification defaults
VERIFICATION_DEFAULT_ENABLED = True
VERIFICATION_DEFAULT_FREE_LIMIT = 3
VERIFICATION_DEFAULT_VALID_MINUTES = 1440  # 24 hours

# Shortlink settings for verification system (read from env)
SHORTLINK_API = os.getenv("SHORTLINK_API", "")
SHORTLINK_URL = os.getenv("SHORTLINK_URL", "")

# Bot username (without @)
BOT_USERNAME = os.getenv("BOT_USERNAME", "Movie_magic_club_bot")

# MongoDB settings
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB = os.getenv("MONGO_DB", "")

# ImgBB API Key (NEW - ADD THIS)
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "e613b8ab80d373ca61a4ad388461ba59")

# Basic sanity check for required vars
if not API_ID or not API_HASH or not BOT_TOKEN:
    print("❌ Please set API_ID, API_HASH, BOT_TOKEN as env variables")
    

