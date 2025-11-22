import os
from fastapi import FastAPI, File, Form, UploadFile
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import asyncio

# Load env vars for bot token, api_id, api_hash, MongoDB URI, channel ID
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # e.g., -100xxxxxxxxxx
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_DB", "movies_magic_club")

client = Client("poster-uploader", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[DB_NAME]

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await client.start()

@app.on_event("shutdown")
async def shutdown_event():
    await client.stop()
    mongo.close()

@app.post("/api/poster/upload")
async def upload_poster(
    movie_title: str = Form(...),
    description: str = Form(...),
    image: UploadFile = File(...)
):
    try:
        # Save to temp file for upload
        tmp_path = f"/tmp/{image.filename}"
        with open(tmp_path, "wb") as f:
            content = await image.read()
            f.write(content)
        
        # Upload to Telegram channel
        tg_msg = await client.send_photo(CHANNEL_ID, tmp_path, caption=f"{movie_title}\n{description}")
        file_id = tg_msg.photo.file_id

        # Get direct file path
        file_info = await client.get_file(file_id)
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"
        
        # Save movie with poster URL in MongoDB
        movie = {
            "title": movie_title,
            "description": description,
            "image_url": image_url,
            "file_id": file_id
        }
        await db.movies.insert_one(movie)
        os.remove(tmp_path)
        return {"success": True, "message": "Poster uploaded and saved!", "url": image_url}
    except Exception as e:
        return {"success": False, "error": str(e)}
