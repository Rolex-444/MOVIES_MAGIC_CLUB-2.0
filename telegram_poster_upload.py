import os
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pyrogram import Client
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import tempfile
import asyncio

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Example: -1001234567890 (as string)
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "movies_magic_club")

# Setup Pyrogram and MongoDB clients
client = Client("poster-uploader", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo[MONGO_DB]

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
        # Save uploaded file to temp
        suffix = os.path.splitext(image.filename)[-1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmpfile:
            content = await image.read()
            tmpfile.write(content)
            tmp_path = tmpfile.name

        # Upload image to Telegram channel
        tg_msg = await client.send_photo(int(CHANNEL_ID), tmp_path, caption=f"{movie_title}\n{description}")
        file_id = tg_msg.photo.file_id

        # Get file path from Telegram to build the URL
        file_info = await client.get_file(file_id)
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

        # Save movie and image URL in MongoDB
        movie = {
            "title": movie_title,
            "description": description,
            "image_url": image_url,
            "file_id": file_id
        }
        await db.movies.insert_one(movie)

        os.remove(tmp_path)
        return JSONResponse({"success": True, "message": "Poster uploaded and saved!", "url": image_url})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# Optional: root check
@app.get("/")
async def root():
    return {"message": "Telegram poster upload microservice is running."}
        
