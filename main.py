# main.py

import os
import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from pyrogram import Client, filters, idle

from db import connect_to_mongo, close_mongo_connection

from routes.movies import router as movies_router
from routes.web import router as web_router
from routes.series_web import router as series_router

# NOTE: admin.py is at project root, not inside routes/
from admin import router as admin_router

from routes.verify import router as verify_router

from config import API_ID, API_HASH, BOT_TOKEN  # from config.py

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")

app = FastAPI()

# Sessions for admin login + verification
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Static files (posters, css, etc.)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Public site routers
app.include_router(movies_router)
app.include_router(web_router)
app.include_router(series_router)

# Admin (login + movies + series) router
app.include_router(admin_router)

# Verification pages
app.include_router(verify_router)

# ---------- Pyrogram bot ----------

bot = Client(
    "movie_webapp_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    text = (
        "👋 Hi!\n\n"
        "Movies Magic Club bot is online.\n"
        "Use the website / web app to browse movies & series. 🎬"
    )
    await message.reply_text(text)


async def run_bot():
    await bot.start()
    print("✅ Pyrogram bot started")
    await idle()
    await bot.stop()
    print("🛑 Pyrogram bot stopped")


# ---------- FastAPI lifecycle ----------

@app.on_event("startup")
async def on_startup():
    await connect_to_mongo()
    asyncio.create_task(run_bot())
    print("🚀 FastAPI app startup complete")


@app.on_event("shutdown")
async def on_shutdown():
    await close_mongo_connection()
    print("🔻 FastAPI app shutting down")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
    
