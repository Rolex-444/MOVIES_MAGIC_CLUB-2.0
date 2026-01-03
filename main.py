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
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-secret")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY", "e613b8ab80d373ca61a4ad388461ba59")

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
app.include_router(comments_router)

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
        await asyncio.sleep(e.value)
        await start_bot_safely()
    except Exception as e:
        print(f"[BOT] ❌ Failed to start bot: {e}")
        print(f"[BOT] ⚠️ Web app will continue running without bot functionality")
        bot_running = False

# ==================== STARTUP/SHUTDOWN ====================
@app.on_event("startup")
async def on_startup():
    await connect_to_mongo()
    print("[APP] ✅ Connected to MongoDB")
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

# ==================== POSTER UPLOAD: IMGBB PRIMARY, CATBOX FALLBACK ====================
@app.post("/api/poster/upload")
async def upload_poster(
    movie_title: str = Form(...),
    description: str = Form(""),
    image: UploadFile = File(...)
):
    """
    Upload poster with smart fallback:
    1. Try ImgBB first (fast, permanent, 16MB limit)
    2. If ImgBB fails, try Catbox (100MB limit, permanent)
    3. Save only the one that succeeds
    """
    tmp_path = None
    poster_url = None
    storage_type = None
    
    try:
        # Save uploaded file to temp
        suffix = os.path.splitext(image.filename)[-1] or ".jpg"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
            content = await image.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        print(f"[POSTER] Starting upload for: {movie_title}")
        
        # ==================== TRY IMGBB FIRST ====================
        try:
            print(f"[POSTER] Trying ImgBB...")
            
            with open(tmp_path, 'rb') as f:
                image_data = base64.b64encode(f.read()).decode('utf-8')
            
            payload = {
                'key': IMGBB_API_KEY,
                'image': image_data,
                'name': movie_title.replace(" ", "_")
            }
            
            response = requests.post(
                "https://api.imgbb.com/1/upload",
                data=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    poster_url = result['data']['url']
                    storage_type = "imgbb"
                    print(f"[POSTER] ✅ ImgBB success: {poster_url}")
                else:
                    raise Exception(f"ImgBB API error: {result.get('error', {}).get('message', 'Unknown')}")
            else:
                raise Exception(f"ImgBB HTTP {response.status_code}")
                
        except Exception as e:
            print(f"[POSTER] ⚠️ ImgBB failed: {e}")
            poster_url = None
        
        # ==================== IF IMGBB FAILED, TRY CATBOX ====================
        if not poster_url:
            try:
                print(f"[POSTER] ImgBB failed, trying Catbox...")
                
                with open(tmp_path, 'rb') as f:
                    files = {'fileToUpload': (image.filename, f, image.content_type or 'image/jpeg')}
                    data = {'reqtype': 'fileupload'}
                    
                    response = requests.post(
                        'https://catbox.moe/user/api.php',
                        files=files,
                        data=data,
                        timeout=20
                    )
                
                if response.status_code == 200 and response.text.startswith('https://files.catbox.moe/'):
                    poster_url = response.text.strip()
                    storage_type = "catbox"
                    print(f"[POSTER] ✅ Catbox success: {poster_url}")
                else:
                    raise Exception(f"Catbox failed: {response.text[:100]}")
                    
            except Exception as e:
                print(f"[POSTER] ❌ Catbox failed: {e}")
                poster_url = None
        
        # ==================== CHECK IF ANY SUCCEEDED ====================
        if not poster_url:
            raise Exception("Both ImgBB and Catbox uploads failed")
        
        # ==================== SAVE TO MONGODB ====================
        movie = {
            "title": movie_title,
            "description": description,
            "poster_url": poster_url,
            "storage_type": storage_type,
            "uploaded_at": datetime.utcnow()
        }
        
        result = await poster_db.movies.insert_one(movie)
        print(f"[POSTER] ✅ Saved to MongoDB: {result.inserted_id}")
        
        # Clean up temp file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        
        return JSONResponse({
            "success": True,
            "message": f"Poster uploaded successfully via {storage_type.upper()}!",
            "url": poster_url,
            "storage": storage_type
        })
        
    except Exception as e:
        print(f"[POSTER] ❌ Upload failed: {e}")
        
        # Clean up temp file
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=200)

# ==================== GET POSTER URL ====================
@app.get("/api/poster/{poster_id}")
async def get_poster_url(poster_id: str):
    """Get poster URL from MongoDB"""
    try:
        poster = await poster_db.movies.find_one({"_id": ObjectId(poster_id)})
        if not poster:
            raise HTTPException(status_code=404, detail="Poster not found")
        
        poster_url = poster.get("poster_url")
        if not poster_url:
            raise HTTPException(status_code=404, detail="No poster URL available")
        
        return JSONResponse({
            "url": poster_url,
            "storage": poster.get("storage_type", "unknown")
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DEBUG ROUTES ====================
@app.get("/debug/config")
async def debug_config():
    return {
        "channel_id": CHANNEL_ID,
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
