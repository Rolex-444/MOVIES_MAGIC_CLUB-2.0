import os
import tempfile
import base64
import asyncio
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.errors import BadRequest, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from datetime import datetime
from bson import ObjectId
import uvicorn

# ==================== MONKEY PATCH FIX ====================
from pyrogram import utils as pyro_utils # type: ignore
pyro_utils.MIN_CHAT_ID = -999999999999
pyro_utils.MIN_CHANNEL_ID = -1007852516352

# ==================== IMPORTS FROM YOUR MODULES ====================
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
from routes.comments import router as comments_router
from routes import notice, admin_notice
from config import API_ID, API_HASH, BOT_TOKEN, CHANNEL_ID, MONGO_URI, MONGO_DB

# ==================== CONFIGURATION ====================
POSTER_CHANNEL_ID = int(os.environ.get("POSTER_CHANNEL_ID", "0"))
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "e613b8ab80d373ca61a4ad388461ba59")  # ADD THIS TO YOUR ENV

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="Movies Magic Club 2.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== INCLUDE ALL YOUR ROUTERS ====================
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
app.include_router(comments_router)  # NEW: Comments system

# ==================== PYROGRAM BOT SETUP ====================
bot = Client(
    "movie_webapp_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

# ==================== BOT STATUS ====================
bot_running = False

# ==================== DATABASE SETUP ====================
mongo_client = AsyncIOMotorClient(MONGO_URI)
poster_db = mongo_client[MONGO_DB if MONGO_DB else "movies_magic_club"]

# ==================== BOT STARTUP WITH ERROR HANDLING ====================
async def start_bot_safely():
    """Start bot in background with proper error handling"""
    global bot_running
    try:
        print("[BOT] Attempting to start Telegram bot...")
        await bot.start()
        bot_running = True
        print("[BOT] ✅ Telegram bot started successfully!")
    except FloodWait as e:
        print(f"[BOT] ⚠️ FloodWait error: Need to wait {e.value} seconds")
        print(f"[BOT] ⚠️ Web app will continue running without bot functionality")
        print(f"[BOT] ⏰ Bot will retry after {e.value // 60} minutes")
        bot_running = False
        # Schedule retry after wait time
        await asyncio.sleep(e.value)
        await start_bot_safely()  # Retry
    except Exception as e:
        print(f"[BOT] ❌ Failed to start bot: {e}")
        print(f"[BOT] ⚠️ Web app will continue running without bot functionality")
        bot_running = False

# ==================== STARTUP/SHUTDOWN ====================
@app.on_event("startup")
async def on_startup():
    # Start database connection
    await connect_to_mongo()
    print("[APP] ✅ Connected to MongoDB")
    
    # Start bot in background (non-blocking)
    asyncio.create_task(start_bot_safely())
    
    print("[APP] ✅ FastAPI web app started successfully!")
    print("[APP] 🌐 Web app is running and ready to serve requests")

@app.on_event("shutdown")
async def on_shutdown():
    await close_mongo_connection()
    if bot_running:
        await bot.stop()
    mongo_client.close()
    print("[APP] 👋 FastAPI app and bot shutting down!")

# ==================== BOT /START COMMAND ====================
@bot.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    text = """🎬 **Welcome to Movies Magic Club!**

Your ultimate destination for movies and series!

**What we offer:**
✅ Latest Movies
✅ Series
✅ Multiple Languages
✅ HD Quality Content
✅ Fast Streaming

**Get Started Below!** 👇"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Open Website", url="https://remote-joceline-rolex44-e142432f.koyeb.app")],
        [InlineKeyboardButton("📢 Join for Updates", url="https://t.me/moviesmagicclub3")]
    ])
    await message.reply_text(text, reply_markup=keyboard)

# ==================== HEALTH CHECK ROUTES ====================
@app.get("/status")
async def status():
    return {
        "status": "ok",
        "web_app": "running",
        "bot_status": "running" if bot_running else "not_running"
    }

@app.get("/")
async def root():
    return {
        "message": "Movies Magic Club API is running.",
        "bot_status": "active" if bot_running else "inactive"
    }

# ==================== HELPER: GET TELEGRAM URL FROM FILE_ID ====================
async def get_telegram_url(file_id: str) -> str:
    """Generate Telegram CDN URL from file_id"""
    try:
        if bot_running:
            file_info = await bot.get_file(file_id)
            return f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
    except Exception as e:
        print(f"[ERROR] Failed to get Telegram URL: {e}")
    return None

# ==================== POSTER UPLOAD API (IMGBB + TELEGRAM HYBRID) ====================
@app.post("/api/poster/upload")
async def upload_poster(
    movie_title: str = Form(...),
    description: str = Form(""),
    image: UploadFile = File(...)
):
    """
    1. Save uploaded image to a temp file.
    2. Upload to Telegram channel (unlimited storage backup) - ONLY IF BOT IS RUNNING.
    3. Upload to ImgBB (fast CDN with better reliability).
    4. Save both references to MongoDB.
    5. FALLBACK: Use Telegram URL if ImgBB fails.
    """
    tmp_path = None
    telegram_file_id = None
    telegram_message_id = None
    telegram_url = None
    imgbb_url = None
    
    try:
        # 1. Save upload to temp file
        suffix = os.path.splitext(image.filename)[-1] or ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            content = await image.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        print(f"[DEBUG] Starting hybrid upload: {movie_title}")
        
        # 2. UPLOAD TO TELEGRAM CHANNEL (ONLY IF BOT IS RUNNING)
        if bot_running and POSTER_CHANNEL_ID != 0:
            try:
                print(f"[DEBUG] Uploading to Telegram channel: {POSTER_CHANNEL_ID}")
                tg_msg = await bot.send_photo(
                    POSTER_CHANNEL_ID,
                    tmp_path,
                    caption=f"🎬 **{movie_title}**\n\n{description}"
                )
                
                # Get file_id from highest-resolution photo
                photo = tg_msg.photo
                if isinstance(photo, list):
                    telegram_file_id = photo[-1].file_id
                else:
                    telegram_file_id = photo.file_id
                telegram_message_id = tg_msg.id
                
                # Generate Telegram CDN URL
                telegram_url = await get_telegram_url(telegram_file_id)
                
                print(f"[SUCCESS] Telegram: file_id={telegram_file_id}")
                print(f"[SUCCESS] Telegram URL: {telegram_url}")
            except Exception as e:
                print(f"[WARNING] Telegram upload failed: {e}")
        else:
            if not bot_running:
                print("[WARNING] Bot not running, skipping Telegram upload")
            else:
                print("[WARNING] POSTER_CHANNEL_ID not configured")
        
        # 3. UPLOAD TO IMGBB (FAST CDN - BETTER THAN CATBOX)
        try:
            print(f"[DEBUG] Uploading to ImgBB...")
            
            # Read image and convert to base64
            with open(tmp_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            # ImgBB API endpoint
            imgbb_api = "https://api.imgbb.com/1/upload"
            
            # Prepare payload
            payload = {
                'key': IMGBB_API_KEY,
                'image': image_data,
                'name': movie_title.replace(" ", "_")
            }
            
            # Make POST request with shorter timeout
            response = requests.post(imgbb_api, data=payload, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    imgbb_url = result['data']['url']
                    print(f"[SUCCESS] ImgBB URL: {imgbb_url}")
                else:
                    raise Exception(f"ImgBB API error: {result.get('error', {}).get('message', 'Unknown error')}")
            else:
                raise Exception(f"ImgBB failed: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"[WARNING] ImgBB upload failed: {e}")
            imgbb_url = None
        
        # 4. CHECK IF AT LEAST ONE SUCCEEDED
        if not telegram_file_id and not imgbb_url:
            raise Exception("Both Telegram and ImgBB uploads failed")
        
        # 5. DETERMINE PRIMARY URL (ImgBB preferred, Telegram as fallback)
        primary_url = imgbb_url if imgbb_url else telegram_url
        
        if not primary_url:
            raise Exception("No valid poster URL generated")
        
        print(f"[SUCCESS] Primary poster URL: {primary_url}")
        
        # 6. SAVE TO MONGODB
        movie = {
            "title": movie_title,
            "description": description,
            "poster_imgbb": imgbb_url,  # Primary (fast, permanent, no ISP blocking)
            "poster_telegram": telegram_url,  # Fallback (unlimited storage)
            "telegram_file_id": telegram_file_id,  # For regenerating URL
            "telegram_message_id": telegram_message_id,
            "poster_primary": primary_url,
            "storage_type": "hybrid" if (imgbb_url and telegram_file_id) else ("imgbb" if imgbb_url else "telegram"),
            "uploaded_at": datetime.utcnow()
        }
        
        result = await poster_db.movies.insert_one(movie)
        print(f"[DEBUG] Movie inserted with ID: {result.inserted_id}")
        
        # 7. Clean up temp file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        
        return JSONResponse({
            "success": True,
            "message": "Poster uploaded and saved!",
            "url": primary_url,
            "storage": "imgbb" if imgbb_url else "telegram"
        })
        
    except BadRequest as e:
        print(f"[ERROR] Poster upload failed (BadRequest): {e.MESSAGE}")
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

# ==================== GET POSTER URL (WITH AUTO-FALLBACK) ====================
@app.get("/api/poster/{poster_id}")
async def get_poster_url(poster_id: str):
    """Get poster URL with automatic fallback from Telegram if ImgBB fails"""
    try:
        poster = await poster_db.movies.find_one({"_id": ObjectId(poster_id)})
        if not poster:
            raise HTTPException(status_code=404, detail="Poster not found")
        
        # Try ImgBB first (fast, permanent, no blocking)
        if poster.get("poster_imgbb"):
            return JSONResponse({
                "url": poster["poster_imgbb"],
                "source": "imgbb",
                "fallback_available": poster.get("telegram_file_id") is not None
            })
        
        # Try saved Telegram URL
        if poster.get("poster_telegram"):
            return JSONResponse({
                "url": poster["poster_telegram"],
                "source": "telegram_cached"
            })
        
        # Fallback: Regenerate URL from file_id - ONLY IF BOT IS RUNNING
        if bot_running and poster.get("telegram_file_id"):
            try:
                telegram_url = await get_telegram_url(poster["telegram_file_id"])
                if telegram_url:
                    return JSONResponse({
                        "url": telegram_url,
                        "source": "telegram",
                        "note": "Regenerated from file_id"
                    })
            except Exception as e:
                print(f"[ERROR] Telegram fallback failed: {e}")
        
        raise HTTPException(status_code=404, detail="No poster sources available")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DEBUG ROUTES ====================
@app.get("/debug/config")
async def debug_config():
    return {
        "channel_id": CHANNEL_ID,
        "poster_channel_id": POSTER_CHANNEL_ID,
        "bot_token_start": BOT_TOKEN[:10],
        "bot_token_length": len(BOT_TOKEN),
        "imgbb_api_configured": bool(IMGBB_API_KEY),
        "bot_running": bot_running
    }

@app.get("/debug/channel")
async def debug_channel():
    if not bot_running:
        return {
            "ok": False,
            "error": "Bot is not running"
        }
    
    try:
        chat = await bot.get_chat(CHANNEL_ID)
        return {
            "ok": True,
            "id": chat.id,
            "title": chat.title,
            "type": str(chat.type)
        }
    except BadRequest as e:
        return {
            "ok": False,
            "error_type": "BadRequest",
            "message": e.MESSAGE
        }
    except Exception as e:
        return {
            "ok": False,
            "error_type": type(e).__name__,
            "message": str(e)
        }

# ==================== RUN SERVER ====================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
