import json
from typing import Dict
from fastapi import WebSocket, WebSocketDisconnect
from storage.meeting_store import MeetingStore

class ConnectionManager:
  def __init__(self):
    self.active_connections: Dict[str, WebSocket] = {}
    self.meeting_stores: Dict[str, MeetingStore] = {}

  def get_or_create_store(self, meeting_id: str) -> MeetingStore:
    if meeting_id not in self.meeting_stores:
      self.meeting_stores[meeting_id] = MeetingStore(meeting_id)
    return self.meeting_stores[meeting_id]

  async def connect(self, websocket: WebSocket, client_id: str):
    await websocket.accept()
    self.active_connections[client_id] = websocket
    print(f"[WebSocket] Client {client_id} connected.")

  def disconnect(self, client_id: str):
    if client_id in self.active_connections:
      del self.active_connections[client_id]
      print(f"[WebSocket] Client {client_id} disconnected.")

  async def handle_client(self, websocket: WebSocket, client_id: str):
    await self.connect(websocket, client_id)
    active_meeting_id = None
    
    try:
      while True:
        # WebSocket can receive text or bytes (binary)
        message = await websocket.receive()

        # Detect normal disconnect from client-sent disconnect frame
        if message.get("type") == "websocket.disconnect":
          break

        try:
          # ── Text message ──────────────────────────────────────────────
          if "text" in message:
            text_data = message["text"]
            try:
              data = json.loads(text_data)
            except json.JSONDecodeError:
              print(f"[WebSocket] Malformed JSON from client {client_id}: {text_data[:100]}")
              continue

            msg_type = data.get("type")
            meeting_id = data.get("meeting_id")
            timestamp = data.get("timestamp")
            payload = data.get("payload", {})

            if not meeting_id:
              continue

            active_meeting_id = meeting_id
            store = self.get_or_create_store(meeting_id)

            if msg_type == "heartbeat":
              # Respond to heartbeat instantly
              await websocket.send_text(json.dumps({
                "type": "heartbeat",
                "status": "ack",
                "timestamp": timestamp
              }))
              await store.log_server_message("Heartbeat acknowledged", "INFO")
              
            elif msg_type == "metadata":
              await store.save_meeting_metadata(payload)
              action = payload.get("action", "update")
              await store.log_server_message(f"Meeting metadata action: {action.upper()}", "INFO")

            elif msg_type == "event":
              await store.save_event(payload)
              event_name = payload.get("type", "unknown")
              await store.log_server_message(f"Event ingested: {event_name.upper()}", "INFO")

          # ── Binary message ────────────────────────────────────────────
          elif "bytes" in message:
            binary_data = message["bytes"]
            if len(binary_data) < 4:
              print(f"[WebSocket] Binary message too small ({len(binary_data)} bytes) from client {client_id}")
              continue
              
            # Read header length (4 bytes big-endian)
            header_len = int.from_bytes(binary_data[0:4], byteorder="big")
            if len(binary_data) < 4 + header_len:
              print(f"[WebSocket] Incomplete binary message header from client {client_id}")
              continue

            # Parse JSON header
            try:
              header_json = binary_data[4:4+header_len].decode("utf-8")
              header = json.loads(header_json)
            except Exception as e:
              print(f"[WebSocket] Failed to decode binary header from client {client_id}: {e}")
              continue

            msg_type = header.get("type")  # "audio" or "video"
            meeting_id = header.get("meeting_id")
            timestamp = header.get("timestamp")
            payload_bytes = binary_data[4+header_len:]

            if not meeting_id or msg_type not in ("audio", "video"):
              print(f"[WebSocket] Invalid binary header content from client {client_id}: {header}")
              continue

            active_meeting_id = meeting_id
            store = self.get_or_create_store(meeting_id)
            
            # Write chunk to disk
            filename = await store.save_media_chunk(msg_type, timestamp, payload_bytes)
            await store.log_server_message(
              f"Saved {msg_type} chunk: {filename} ({len(payload_bytes)} bytes)", "INFO"
            )

            # Enqueue to Audio Engine workers if it's an audio chunk
            if msg_type == "audio":
              try:
                chunk_index = int(filename.split(".")[0])
                from engine.audio import enqueue_audio_chunk, AudioChunk
                audio_chunk = AudioChunk(
                    meeting_id=meeting_id,
                    timestamp=timestamp,
                    chunk_index=chunk_index,
                    data=payload_bytes,
                    file_path=str(store.audio_dir / filename)
                )
                await enqueue_audio_chunk(audio_chunk)
              except Exception as e:
                print(f"[WebSocket] Error enqueuing audio chunk: {e}")

            # Enqueue to Video Engine workers if it's a video chunk
            elif msg_type == "video":
              try:
                chunk_index = int(filename.split(".")[0])
                from engine.video import enqueue_video_chunk, VideoChunk
                video_chunk = VideoChunk(
                    meeting_id=meeting_id,
                    timestamp=timestamp,
                    chunk_index=chunk_index,
                    data=payload_bytes,
                    file_path=str(store.video_dir / filename)
                )
                await enqueue_video_chunk(video_chunk)
              except Exception as e:
                print(f"[WebSocket] Error enqueuing video chunk: {e}")

        except Exception as loop_err:
          # A single bad message must NEVER kill the whole WebSocket session.
          print(f"[WebSocket] Non-fatal error processing message from client {client_id}: {loop_err}")
          continue

    except WebSocketDisconnect:
      self.disconnect(client_id)
      if active_meeting_id:
        try:
          store = self.get_or_create_store(active_meeting_id)
          await store.log_server_message(f"Client {client_id} disconnected from WebSocket stream.", "WARN")
        except Exception:
          pass
    except Exception as e:
      print(f"[WebSocket] Fatal error handling client {client_id}: {e}")
      self.disconnect(client_id)
      if active_meeting_id:
        try:
          store = self.get_or_create_store(active_meeting_id)
          await store.log_server_message(f"Fatal WebSocket error: {str(e)}", "ERROR")
        except Exception:
          pass

manager = ConnectionManager()

