import os

# Telegram Bot credentials from environment variables
API_ID = int(os.getenv("API_ID", ""))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

VERIFICATION_DEFAULT_ENABLED = True
VERIFICATION_DEFAULT_FREE_LIMIT = 3
VERIFICATION_DEFAULT_VALID_MINUTES = 1440 # 24 hours

# Shortlink settings for verification system (read from env)
SHORTLINK_API = os.getenv("SHORTLINK_API", "")
SHORTLINK_URL = os.getenv("SHORTLINK_URL", "")

# Add this line
BOT_USERNAME = os.getenv("BOT_USERNAME", "Movie_magic_club_bot")  # Without @

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("❌ Please set API_ID, API_HASH, BOT_TOKEN as env variables")


