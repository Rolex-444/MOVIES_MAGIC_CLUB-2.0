import os

# Telegram Bot credentials from environment variables
API_ID = int(os.getenv("API_ID", "29542645"))
API_HASH = os.getenv("API_HASH", "06e505b8418565356ae79365df5d69e0")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7838310659:AAFj9OEp9pQ4UJT5Lk3kWAEsgnNsX3JansY")

VERIFICATION_DEFAULT_ENABLED = True
VERIFICATION_DEFAULT_FREE_LIMIT = 3
VERIFICATION_DEFAULT_VALID_MINUTES = 1440 # 24 hours

# Shortlink settings for verification system (read from env)
SHORTLINK_API = os.getenv("SHORTLINK_API", "139ebf8c6591acc6a69db83f200f2285874dbdbf")
SHORTLINK_URL = os.getenv("SHORTLINK_URL", "http://arolinks.com")

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("❌ Please set API_ID, API_HASH, BOT_TOKEN as env variables")

