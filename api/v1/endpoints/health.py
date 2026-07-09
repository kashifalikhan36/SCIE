from fastapi import APIRouter
from database.mongodb import MongoClientManager
from database.redis import RedisClientManager

router = APIRouter()

@router.get("/health")
async def health_check():
  mongo_ok = await MongoClientManager.get_instance().check_connection()
  redis_ok = await RedisClientManager.get_instance().check_connection()
  
  return {
      "status": "ok" if (mongo_ok and redis_ok) else "degraded",
      "mongodb": "connected" if mongo_ok else "disconnected",
      "redis": "connected" if redis_ok else "disconnected"
  }
