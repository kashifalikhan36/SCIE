import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from core.config import settings

async def reset_db():
    print("Connecting to MongoDB...")
    mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    db = mongo_client[settings.MONGO_DB]
    
    collections = await db.list_collection_names()
    for coll in collections:
        print(f"Dropping collection: {coll}")
        await db[coll].drop()
    
    print("MongoDB cleaned.")
    
    if settings.REDIS_URL:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
    else:
        redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            password=settings.REDIS_PASSWORD
        )
    print("Flushing Redis DB...")
    await redis_client.flushdb()
    print("Redis cleaned.")
    
if __name__ == "__main__":
    asyncio.run(reset_db())
