import os
import tempfile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from pyrogram import Client, filters
from pyrogram.errors import BadRequest
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# ---- FIX for Pyrogram Peer ID bug (MIN_* constants) ----
# Based on official PR: MIN_CHANNEL_ID = -1007852516352, MIN_CHAT_ID = -999999999999
# https://github.com/pyrogram/pyrogram/pull/1430
from pyrogram import utils as pyrou  # type: ignore
pyrou.MIN_CHAT_ID = -999_999_999_999       # allow all new groups
pyrou.MIN_CHANNEL_ID = -1_007_852_516_352  # allow all new channels
# ---- END FIX ----

from motor.motor_asyncio import AsyncIOMotorClient
import requests  # for Telegram HTTP getFile

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
from routes import notice, admin_notice

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    CHANNEL_ID,
    MONGO_URI,
    MONGO_DB,
)

# -------------------------------------------------------------------
# FastAPI app setup
# -------------------------------------------------------------------

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")

app = FastAPI(title="Movies Magic Club 2.0")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(web_router)
app.include_router(movies_router)
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
app.include_router(notice.router)
app.include_router(admin_notice.router)

# -------------------------------------------------------------------
# Telegram bot client (Pyrogram)
# -------------------------------------------------------------------

bot = Client(
    "movie_webapp_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)

# Separate Mongo client for poster collection
mongo_client = AsyncIOMotorClient(MONGO_URI)
poster_db = mongo_client[MONGO_DB if MONGO_DB else "movies_magic_club"]





# -------------------------------------------------------------------
# Startup & shutdown
# -------------------------------------------------------------------


@app.on_event("startup")
async def on_startup():
    await connect_to_mongo()
    await bot.start()
    print("🚀 FastAPI app and bot startup complete!")


@app.on_event("shutdown")
async def on_shutdown():
    await close_mongo_connection()
    await bot.stop()
    mongo_client.close()
    print("🔻 FastAPI app and bot shutting down!")


@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    # Eye-catching welcome message
    text = (
        "🎬 **Welcome to Movies Magic Club!** 🎬\n\n"
        "🌟 Your ultimate destination for movies and series!\n\n"
        "✨ **What we offer:**\n"
        "📽️ Latest Movies & Series\n"
        "🎯 Multiple Languages\n"
        "🔥 HD Quality Content\n"
        "⚡ Fast Streaming\n\n"
        "👇 **Get Started Below!**"
    )
    
    # Inline keyboard with two buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🌐 Open Website", 
                url="https://preferred-lesya-rolex44-c5202a04.koyeb.app/"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Join for Updates", 
                url="https://t.me/movies_magic_club3"
            )
        ]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)
# Health / root
# -------------------------------------------------------------------


@app.get("/status")
async def status():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "Movies Magic Club API is running."}


# -------------------------------------------------------------------
# Poster upload API
# -------------------------------------------------------------------


@app.post("/api/poster/upload")
async def upload_poster(
    movie_title: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...),
):
    """
    1. Save uploaded image to a temp file.
    2. Send to Telegram channel as photo.
    3. Call Telegram HTTP getFile to build file URL.
    4. Save record to MongoDB.
    """
    tmp_path = None

    try:
        # 1) Save upload to temp file
        suffix = os.path.splitext(image.filename or "")[-1] or ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpfile:
            content = await image.read()
            tmpfile.write(content)
            tmp_path = tmpfile.name

        print(f"[DEBUG] Uploading image to Telegram: {tmp_path}")

        # 2) Send photo to channel
        tg_msg = await bot.send_photo(
            CHANNEL_ID,
            tmp_path,
            caption=f"{movie_title}\n{description}",
        )

        # 3) Get highest-resolution photo file_id
        photo = tg_msg.photo
        if isinstance(photo, list):
            file_id = photo[-1].file_id
        else:
            file_id = photo.file_id

        print(f"[DEBUG] Telegram file_id: {file_id}")

        # 4) Use Telegram HTTP Bot API getFile (avoid Pyrogram async-generator bug)
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": file_id},
            timeout=20,
        )
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"getFile failed: {data}")

        file_path = data["result"]["file_path"]
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        print(f"[DEBUG] Telegram image URL: {image_url}")

        # 5) Save movie record in Mongo
        movie = {
            "title": movie_title,
            "description": description,
            "image_url": image_url,
            "file_id": file_id,
        }
        result = await poster_db.movies.insert_one(movie)
        print(f"[DEBUG] Movie inserted with ID: {result.inserted_id}")

        # 6) Clean up temp file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

        return JSONResponse(
            {
                "success": True,
                "message": "Poster uploaded and saved!",
                "url": image_url,
            }
        )

    except BadRequest as e:
        print(f"[ERROR] Poster upload failed (BadRequest): {e.MESSAGE}")
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return JSONResponse(
            {"success": False, "error": e.MESSAGE},
            status_code=200,
        )

    except Exception as e:
        print(f"[ERROR] Poster upload failed: {e}")
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return JSONResponse(
            {"success": False, "error": str(e)},
            status_code=200,
        )


# -------------------------------------------------------------------
# Debug endpoints
# -------------------------------------------------------------------


@app.get("/debug/config")
async def debug_config():
    return {
        "channel_id": CHANNEL_ID,
        "bot_token_start": BOT_TOKEN[:10],
        "bot_token_length": len(BOT_TOKEN),
    }


@app.get("/debug/channel")
async def debug_channel():
    try:
        chat = await bot.get_chat(CHANNEL_ID)
        return {
            "ok": True,
            "id": chat.id,
            "title": chat.title,
            "type": str(chat.type),
        }
    except BadRequest as e:
        return {
            "ok": False,
            "error_type": "BadRequest",
            "message": e.MESSAGE,
        }
    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "message": str(e),
        }


# -------------------------------------------------------------------
# Local dev entrypoint
# -------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
    
