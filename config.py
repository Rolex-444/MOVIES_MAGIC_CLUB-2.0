import os

# Telegram Bot credentials from environment variables
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not API_ID or not API_HASH or not BOT_TOKEN:
    print("❌ Please set API_ID, API_HASH, BOT_TOKEN as env variables")
