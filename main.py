import os
import tempfile
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pyrogram import Client, filters
from pyrogram.errors import BadRequest
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ---- MONKEY PATCH FOR PYROGRAM ----
from pyrogram import utils as pyrou  # type: ignore
pyrou.MIN_CHAT_ID = -999999999999
pyrou.MIN_CHANNEL_ID = -1007852516352
# ---- END FIX ----

from motor.motor_asyncio import AsyncIOMotorClient
import requests

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

from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, MONGO_URI, MONGO_DB

SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")

app = FastAPI(title="Movies Magic Club 2.0")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ROUTERS
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

# BOT CLIENT
bot = Client(
    "movie_webapp_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

mongo_client = AsyncIOMotorClient(MONGO_URI)
poster_db = mongo_client[MONGO_DB if MONGO_DB else "movies_magic_club"]

@app.on_event("startup")
async def on_startup():
    await connect_to_mongo()
    await bot.start()
    print("FastAPI app and bot startup complete!")

@app.on_event("shutdown")
async def on_shutdown():
    await close_mongo_connection()
    await bot.stop()
    mongo_client.close()
    print("FastAPI app and bot shutting down!")

@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    text = """🎬 **Welcome to Movies Magic Club!** 🎬

Your ultimate destination for movies and series! 🍿

✨ **What we offer:**
📽️ Latest Movies & Series
🌍 Multiple Languages
🎥 HD Quality Content
⚡ Fast Streaming

🚀 **Get Started Below!**"""

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Open Website", url="https://remote-joceline-rolex44-e142432f.koyeb.app")],
        [InlineKeyboardButton("📢 Join for Updates", url="https://t.me/moviesmagicclub3")]
    ])
    
    await message.reply_text(text, reply_markup=keyboard)

@app.get("/status")
async def status():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Movies Magic Club API is running."}

# ---- FIXED POSTER UPLOAD ----
@app.post("/api/poster/upload")
async def api_poster_upload(
    movie_title: str = Form(...),
    description: str = Form(""), 
    image: UploadFile = File(...)
):
    tmp_path = None
    try:
        # 1. Save to temp file
        suffix = os.path.splitext(image.filename)[1] or ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            content = await image.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        print(f"[DEBUG] Uploading to Catbox: {tmp_path}")

        # 2. Upload to Catbox.moe (Free, No API Key Required)
        catbox_url = "https://catbox.moe/user/api.php"
        
        with open(tmp_path, 'rb') as f:
            files = {'fileToUpload': (image.filename, f, 'image/jpeg')}
            data = {
                'reqtype': 'fileupload',
            }
            
            response = requests.post(catbox_url, files=files, data=data, timeout=30)
        
        if response.status_code == 200:
            final_image_url = response.text.strip()
            
            # Validate URL
            if final_image_url.startswith('http'):
                print(f"[SUCCESS] Permanent URL: {final_image_url}")
            else:
                raise Exception(f"Invalid Catbox response: {final_image_url}")
        else:
            raise Exception(f"Catbox upload failed: HTTP {response.status_code}")

        # 3. Save to MongoDB
        movie = {
            "title": movie_title,
            "description": description,
            "image_url": final_image_url,
            "file_id": "catbox_hosted",
        }
        
        result = await poster_db.movies.insert_one(movie)
        print(f"[DEBUG] Movie inserted with ID: {result.inserted_id}")

        # Clean up
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass

        return JSONResponse({
            "success": True,
            "message": "Poster uploaded and saved!",
            "url": final_image_url
        })

    except BadRequest as e:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return JSONResponse({"success": False, "error": e.MESSAGE}, status_code=200)
        
    except Exception as e:
        print(f"[ERROR] Poster upload failed: {e}")
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return JSONResponse({"success": False, "error": str(e)}, status_code=200)
        
            


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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
