import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from core.config import settings
from api.v1.api import api_router
from websocket.manager import manager

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
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
