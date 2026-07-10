import uvicorn
import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from api.v1.api import api_router
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

  from engine.audio import AudioEngineWorkerManager
  audio_worker_manager = AudioEngineWorkerManager.get_instance()
  audio_worker_manager.start()

  from engine.video import VideoEngineWorkerManager
  video_worker_manager = VideoEngineWorkerManager.get_instance()
  video_worker_manager.start()

  from engine.transcript import TranscriptEngineWorkerManager
  transcript_worker_manager = TranscriptEngineWorkerManager.get_instance()
  transcript_worker_manager.start()
  
  from engine.identity.workers import IdentityWorkerManager
  identity_worker_manager = IdentityWorkerManager.get_instance()
  identity_worker_manager.start()

  from engine.conversation.workers import ConversationWorkerManager
  conversation_worker_manager = ConversationWorkerManager.get_instance()
  conversation_worker_manager.start()

  from engine.behavior.workers import BehaviorWorkerManager
  behavior_worker_manager = BehaviorWorkerManager.get_instance()
  behavior_worker_manager.start()

  from engine.fusion.workers import FusionWorkerManager
  fusion_worker_manager = FusionWorkerManager.get_instance()
  fusion_worker_manager.start()
  
  yield
  
  # Shutdown: Close database connections gracefully and stop background workers
  await audio_worker_manager.stop()
  await video_worker_manager.stop()
  await transcript_worker_manager.stop()
  await identity_worker_manager.stop()
  await conversation_worker_manager.stop()
  await behavior_worker_manager.stop()
  await fusion_worker_manager.stop()
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

from websocket.dashboard_manager import dashboard_manager

# WebSocket endpoint for real-time Dashboard updates
@app.websocket("/ws/dashboard/{meeting_id}")
async def dashboard_websocket_endpoint(websocket: WebSocket, meeting_id: str):
  await dashboard_manager.connect(websocket, meeting_id)
  try:
      while True:
          # Wait for any messages from the client (e.g., heartbeat)
          data = await websocket.receive_text()
          if data == "ping":
              await websocket.send_text("pong")
  except Exception:
      dashboard_manager.disconnect(websocket, meeting_id)

if __name__ == "__main__":
  uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
