# main.py

import os
import asyncio
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from pyrogram import Client, filters, idle
from motor.motor_asyncio import AsyncIOMotorClient

from db import connect_to_mongo, close_mongo_connection
from routes.movies import router as movies_router
from routes.web import router as web_router
from routes.series_web import router as series_router
from routes.admin_auth import router as admin_auth_router
from routes.admin_movies import router as admin_movies_router
from routes.admin_series import router as admin_series_router
from routes.admin_series_seasons import router as admin_series_seasons_router
from routes.verify import router as verify_router
from routes.admin_episodes import router as admin_episodes_router
from routes.admin_verification import router as admin_verification_router
from routes.support import router as support_router
from routes.legal import router as legal_router

from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, MONGO_URI, MONGO_DB  # updated import

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")

app = FastAPI()

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(movies_router)
app.include_router(web_router)
app.include_router(series_router)
app.include_router(admin_auth_router)
app.include_router(admin_movies_router)
app.include_router(admin_series_router)
app.include_router(admin_series_seasons_router)
app.include_router(verify_router)
app.include_router(admin_episodes_router)
app.include_router(admin_verification_router)
app.include_router(support_router)
app.include_router(legal_router)

# ---------- Main Pyrogram Bot ----------
bot = Client(
    "movie_webapp_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True  # session stored in RAM, no sqlite file
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

# ---------- Poster Upload Integration ----------
poster_client = Client(
    "poster-uploader",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)
poster_mongo = AsyncIOMotorClient(MONGO_URI)
poster_db = poster_mongo[MONGO_DB if MONGO_DB else "movies_magic_club"]

@app.on_event("startup")
async def on_startup():
    await connect_to_mongo()
    asyncio.create_task(run_bot())
    await poster_client.start()
    print("🚀 FastAPI app and poster_client startup complete!")

@app.on_event("shutdown")
async def on_shutdown():
    await close_mongo_connection()
    await poster_client.stop()
    poster_mongo.close()
    print("🔻 FastAPI app and poster_client shutting down!")

@app.post("/api/poster/upload")
async def upload_poster(
    movie_title: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...)
):
    try:
        suffix = os.path.splitext(image.filename)[-1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpfile:
            content = await image.read()
            tmpfile.write(content)
            tmp_path = tmpfile.name

        print(f"[DEBUG] Uploading image to Telegram: {tmp_path}")
        tg_msg = await poster_client.send_photo(int(CHANNEL_ID), tmp_path, caption=f"{movie_title}\n{description}")
        file_id = tg_msg.photo.file_id
        print(f"[DEBUG] Telegram file_id: {file_id}")

        file_info = await poster_client.get_file(file_id)
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        print(f"[DEBUG] Telegram image URL: {image_url}")

        movie = {
            "title": movie_title,
            "description": description,
            "image_url": image_url,
            "file_id": file_id
        }
        result = await poster_db.movies.insert_one(movie)
        os.remove(tmp_path)
        print(f"[DEBUG] Movie inserted with ID: {result.inserted_id}")

        return JSONResponse({"success": True, "message": "Poster uploaded and saved!", "url": image_url})
    except Exception as e:
        print(f"[ERROR] Poster upload failed: {e}")
        return JSONResponse({"success": False, "error": str(e)})

# ---------- Root Message ----------
@app.get("/")
async def root():
    return {"message": "Movies Magic Club API is running."}

# ---------- Uvicorn Entrypoint ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
