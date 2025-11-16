import os
import motor.motor_asyncio

MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "sr_movies")

mongo_client = None
mongo_db = None


async def connect_to_mongo():
    """
    Call this on app startup.
    """
    global mongo_client, mongo_db

    if not MONGO_URI:
        print("⚠️ MONGO_URI not set, skipping Mongo connection")
        return

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    mongo_db = mongo_client[DB_NAME]
    print(f"✅ Connected to MongoDB (DB={DB_NAME})")


async def close_mongo_connection():
    """
    Call this on app shutdown.
    """
    global mongo_client

    if mongo_client:
        mongo_client.close()
        print("🔻 MongoDB connection closed")


def get_db():
    """
    Use this inside routes to get current DB.
    """
    return mongo_db
