import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any
from core.config import settings

class MeetingStore:
  def __init__(self, meeting_id: str):
    self.meeting_id = meeting_id
    self.base_dir = Path(settings.SAVE_DIR) / "meetings" / meeting_id
    self.metadata_dir = self.base_dir / "metadata"
    self.events_dir = self.base_dir / "events"
    self.audio_dir = self.base_dir / "audio"
    self.video_dir = self.base_dir / "video"
    self.logs_dir = self.base_dir / "logs"
    
    # Initialize directory structure
    self._init_directories()

  def _init_directories(self):
    for d in [self.metadata_dir, self.events_dir, self.audio_dir, self.video_dir, self.logs_dir]:
      try:
        d.mkdir(parents=True, exist_ok=True)
      except Exception as e:
        print(f"[MeetingStore] Failed to create directory {d}: {e}")

  async def log_server_message(self, message: str, level: str = "INFO"):
    import datetime
    log_file = self.logs_dir / "server.log"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_line = f"[{timestamp}] [{level}] {message}\n"
    
    def _write():
      try:
        # Ensure log directory exists (guard against race condition)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
          f.write(log_line)
      except Exception as ex:
        print(f"[MeetingStore] Failed to write log: {ex}")

    try:
      await asyncio.to_thread(_write)
    except Exception as ex:
      print(f"[MeetingStore] log_server_message thread error: {ex}")

  async def save_meeting_metadata(self, metadata: Dict[str, Any]):
    meeting_file = self.metadata_dir / "meeting.json"
    
    def _write():
      # If metadata file exists, merge/update
      current = {}
      if meeting_file.exists():
        try:
          with open(meeting_file, "r", encoding="utf-8") as f:
            current = json.load(f)
        except Exception:
          pass
      
      current.update(metadata)
      current["updated_at"] = metadata.get("timestamp") or current.get("updated_at")
      
      with open(meeting_file, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)

    await asyncio.to_thread(_write)
    await self.log_server_message("Updated meeting metadata in meeting.json")

  async def save_participants_metadata(self, participants: List[Dict[str, Any]], timestamp: int):
    participants_file = self.metadata_dir / "participants.json"
    
    def _write():
      # Read existing participants to maintain state
      current_state = {}
      if participants_file.exists():
        try:
          with open(participants_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            current_state = data.get("participants", {})
        except Exception:
          pass

      # Update current state with the incoming array of participant updates
      for p in participants:
        p_id = p.get("id")
        if p_id:
          current_state[p_id] = {
            "display_name": p.get("display_name"),
            "camera": p.get("camera", "off"),
            "mic": p.get("mic", "off"),
            "screen_share": p.get("screen_share", "off"),
            "is_speaking": p.get("is_speaking", False),
            "last_seen": timestamp
          }

      with open(participants_file, "w", encoding="utf-8") as f:
        json.dump({"participants": current_state, "last_updated": timestamp}, f, indent=2)

    await asyncio.to_thread(_write)
    # Don't log this to server.log to avoid log bloat during high-frequency checks

  async def save_event(self, event: Dict[str, Any]):
    events_file = self.events_dir / "events.jsonl"
    event_str = json.dumps(event) + "\n"
    
    def _write():
      with open(events_file, "a", encoding="utf-8") as f:
        f.write(event_str)

    await asyncio.to_thread(_write)
    
    # Update participants.json if this is a join/leave/mic/camera/screenshare event
    event_type = event.get("type")
    p_id = event.get("participant_id")
    p_name = event.get("display_name")
    
    if event_type and p_id:
      timestamp = event.get("timestamp") or int(event.get("timestamp", 0))
      
      # Build a single-item update list for the participants updater
      update_payload = []
      if event_type == "participant_join":
        update_payload.append({
          "id": p_id,
          "display_name": p_name,
          "camera": event.get("camera", "off"),
          "mic": event.get("mic", "off"),
          "screen_share": event.get("screen_share", "off"),
          "is_speaking": False
        })
      elif event_type == "participant_leave":
        # Remove from participants list entirely or mark as left
        # We'll mark them as "left" or delete them
        # Let's delete them to keep the active participants file clean
        def _remove_participant():
          p_file = self.metadata_dir / "participants.json"
          if p_file.exists():
            try:
              with open(p_file, "r+", encoding="utf-8") as f:
                data = json.load(f)
                parts = data.get("participants", {})
                if p_id in parts:
                  del parts[p_id]
                f.seek(0)
                json.dump({"participants": parts, "last_updated": timestamp}, f, indent=2)
                f.truncate()
            except Exception:
              pass
        await asyncio.to_thread(_remove_participant)
      else:
        # State changes
        change = {"id": p_id, "display_name": p_name}
        
        # Load existing participant state
        def _get_existing():
          p_file = self.metadata_dir / "participants.json"
          if p_file.exists():
            try:
              with open(p_file, "r") as f:
                return json.load(f).get("participants", {}).get(p_id, {})
            except Exception:
              pass
          return {}
          
        current_p = await asyncio.to_thread(_get_existing)
        
        if event_type == "camera_on":
          change["camera"] = "on"
          change["mic"] = current_p.get("mic", "off")
          change["screen_share"] = current_p.get("screen_share", "off")
        elif event_type == "camera_off":
          change["camera"] = "off"
          change["mic"] = current_p.get("mic", "off")
          change["screen_share"] = current_p.get("screen_share", "off")
        elif event_type == "mic_on":
          change["mic"] = "on"
          change["camera"] = current_p.get("camera", "off")
          change["screen_share"] = current_p.get("screen_share", "off")
        elif event_type == "mic_off":
          change["mic"] = "off"
          change["camera"] = current_p.get("camera", "off")
          change["screen_share"] = current_p.get("screen_share", "off")
        elif event_type == "screen_share":
          change["screen_share"] = event.get("state", "off")
          change["camera"] = current_p.get("camera", "off")
          change["mic"] = current_p.get("mic", "off")
        elif event_type == "speaker_active":
          change["is_speaking"] = True
          change["camera"] = current_p.get("camera", "off")
          change["mic"] = current_p.get("mic", "off")
          change["screen_share"] = current_p.get("screen_share", "off")
          
        if len(change) > 2:
          update_payload.append(change)
          
      if update_payload:
        await self.save_participants_metadata(update_payload, timestamp)

  async def save_media_chunk(self, media_type: str, timestamp: int, payload: bytes) -> str:
    target_dir = self.audio_dir if media_type == "audio" else self.video_dir
    extension = "webm"
    
    def _write_chunk():
      # Scan directory to find the next sequential index
      existing = list(target_dir.glob(f"*.{extension}"))
      max_idx = 0
      for f in existing:
        try:
          idx = int(f.stem)
          if idx > max_idx:
            max_idx = idx
        except ValueError:
          pass
      
      next_idx = max_idx + 1
      filename = f"{next_idx:06d}.{extension}"
      filepath = target_dir / filename
      
      with open(filepath, "wb") as f:
        f.write(payload)
      return filename

    filename = await asyncio.to_thread(_write_chunk)
    
    # Save the chunk event to events.jsonl to preserve timestamp association
    chunk_event = {
      "type": f"{media_type}_chunk",
      "timestamp": timestamp,
      "filename": filename,
      "size_bytes": len(payload)
    }
    await self.save_event(chunk_event)
    
    return filename
