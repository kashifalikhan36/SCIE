import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from api.v1.api import api_router
from websocket.manager import manager
from database.mongodb import MongoClientManager
from database.redis import RedisClientManager

@asynccontextmanager
async def lifespan(app: FastAPI):
  # Startup: Initialize connection managers
  mongo_manager = MongoClientManager.get_instance()
  mongo_manager.initialize()
  
  redis_manager = RedisClientManager.get_instance()
  redis_manager.initialize()
  
  # Run async connection checks in the background (non-blocking)
  asyncio.create_task(mongo_manager.check_connection())
  asyncio.create_task(redis_manager.check_connection())

  # Initialize and start background Audio and Video Engine workers
  from engine.audio import AudioEngineWorkerManager
  audio_worker_manager = AudioEngineWorkerManager.get_instance()
  audio_worker_manager.start()

  from engine.video import VideoEngineWorkerManager
  video_worker_manager = VideoEngineWorkerManager.get_instance()
  video_worker_manager.start()
  
  yield
  
  # Shutdown: Close database connections gracefully and stop background workers
  await audio_worker_manager.stop()
  await video_worker_manager.stop()
  await mongo_manager.close()
  await redis_manager.close()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST endpoints under v1 prefix
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
  return {"status": "running", "project": settings.PROJECT_NAME}

# WebSocket endpoint for real-time Chrome Extension streaming ingestion
@app.websocket("/ws/meeting")
async def websocket_endpoint(websocket: WebSocket):
  client_id = f"{websocket.client.host}:{websocket.client.port}"
  await manager.handle_client(websocket, client_id)

if __name__ == "__main__":
  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
