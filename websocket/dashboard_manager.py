import json
import asyncio
from typing import Dict, List
from fastapi import WebSocket, WebSocketDisconnect
from engine.fusion.state_manager import fusion_state_manager

class DashboardConnectionManager:
    def __init__(self):
        # meeting_id -> list of connected WebSockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # meeting_id -> polling task
        self.polling_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, meeting_id: str):
        await websocket.accept()
        if meeting_id not in self.active_connections:
            self.active_connections[meeting_id] = []
        self.active_connections[meeting_id].append(websocket)
        
        # Start polling task for this meeting if not already running
        if meeting_id not in self.polling_tasks or self.polling_tasks[meeting_id].done():
            self.polling_tasks[meeting_id] = asyncio.create_task(self._poll_and_broadcast(meeting_id))
            
        print(f"[WebSocket Dashboard] Client connected to meeting: {meeting_id}")

    def disconnect(self, websocket: WebSocket, meeting_id: str):
        if meeting_id in self.active_connections:
            if websocket in self.active_connections[meeting_id]:
                self.active_connections[meeting_id].remove(websocket)
            
            # If no clients left for this meeting, stop the polling task
            if not self.active_connections[meeting_id]:
                task = self.polling_tasks.get(meeting_id)
                if task and not task.done():
                    task.cancel()
                del self.active_connections[meeting_id]
                if meeting_id in self.polling_tasks:
                    del self.polling_tasks[meeting_id]
                    
        print(f"[WebSocket Dashboard] Client disconnected from meeting: {meeting_id}")

    async def _poll_and_broadcast(self, meeting_id: str):
        """Background task that polls Redis and broadcasts state to connected clients."""
        try:
            while True:
                # 1. Get Ranking
                ranking = await fusion_state_manager.get_latest_ranking(meeting_id)
                
                # 2. Get Participants
                participants = await fusion_state_manager.get_all_participant_states(meeting_id)
                
                # We could also fetch recent events from MongoDB if needed, but for now Redis state is enough
                # Prepare payload
                payload = {
                    "type": "live_state_update",
                    "meeting_id": meeting_id,
                    "data": {
                        "ranking": ranking.model_dump() if ranking else None,
                        "participants": {pid: state.model_dump() for pid, state in participants.items()}
                    }
                }
                
                message = json.dumps(payload)
                
                # Broadcast
                await self._broadcast(meeting_id, message)
                
                # Poll every 1 second
                await asyncio.sleep(1.0)
                
        except asyncio.CancelledError:
            print(f"[WebSocket Dashboard] Polling task cancelled for meeting: {meeting_id}")
        except Exception as e:
            print(f"[WebSocket Dashboard] Error in polling task: {e}")

    async def _broadcast(self, meeting_id: str, message: str):
        if meeting_id in self.active_connections:
            # We copy the list to avoid modification during iteration
            for connection in list(self.active_connections[meeting_id]):
                try:
                    await connection.send_text(message)
                except Exception:
                    self.disconnect(connection, meeting_id)

dashboard_manager = DashboardConnectionManager()
