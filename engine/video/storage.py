import logging
from typing import Dict, Any, List
from database.mongodb import get_mongo_db
from engine.video.schemas import VisualEvidence
from engine.video.constants import (
    MONGO_MEETINGS_COL,
    MONGO_FRAMES_COL,
    MONGO_TRACKS_COL,
    MONGO_EMBEDDINGS_COL,
    MONGO_EVIDENCE_COL
)
from engine.video.exceptions import StorageError

logger = logging.getLogger("SCIE.video_engine.storage")

class VideoStorageManager:
  """Handles MongoDB database operations for all historical video engine artifacts."""

  async def save_meeting_info(self, meeting_id: str, metadata: Dict[str, Any]):
    """Persists meeting metadata if it doesn't exist or updates it."""
    db = get_mongo_db()
    if db is None:
      logger.warning("MongoDB unavailable; skipping visual meeting info save.")
      return

    try:
      col = db[MONGO_MEETINGS_COL]
      await col.update_one(
          {"meeting_id": meeting_id},
          {"$set": {**metadata, "meeting_id": meeting_id}},
          upsert=True
      )
      logger.debug(f"Saved meeting metadata in MongoDB for {meeting_id}")
    except Exception as e:
      logger.error(f"Failed to save meeting metadata to MongoDB: {e}")

  async def save_video_frame(self, meeting_id: str, frame_data: Dict[str, Any]):
    """Saves a record of a decoded/sampled video frame."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_FRAMES_COL]
      await col.insert_one({**frame_data, "meeting_id": meeting_id})
      logger.debug(f"Saved video frame record in MongoDB.")
    except Exception as e:
      logger.error(f"Failed to save video frame in MongoDB: {e}")

  async def save_face_track(self, meeting_id: str, track_data: Dict[str, Any]):
    """Saves track state history for offline evaluation."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_TRACKS_COL]
      await col.insert_one({**track_data, "meeting_id": meeting_id})
      logger.debug(f"Saved face track record in MongoDB.")
    except Exception as e:
      logger.error(f"Failed to save face track in MongoDB: {e}")

  async def save_face_embedding(self, meeting_id: str, track_id: str, embedding: List[float], timestamp: int):
    """Saves face embedding vectors, avoiding duplication by unique track_id."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_EMBEDDINGS_COL]
      # Prevent duplicates of identical tracks
      await col.update_one(
          {"meeting_id": meeting_id, "track_id": track_id},
          {"$setOnInsert": {
              "meeting_id": meeting_id,
              "track_id": track_id,
              "embedding": embedding,
              "created_at": timestamp
          }},
          upsert=True
      )
      logger.debug(f"Saved unique face embedding in MongoDB for track {track_id}")
    except Exception as e:
      logger.error(f"Failed to save face embedding in MongoDB: {e}")

  async def save_visual_evidence(self, evidence: VisualEvidence):
    """Saves final assembled VisualEvidence objects to MongoDB."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_EVIDENCE_COL]
      doc = evidence.model_dump()
      await col.insert_one(doc)
      logger.info(f"Persisted VisualEvidence record in MongoDB for track {evidence.track_id}")
    except Exception as e:
      logger.error(f"Failed to save visual evidence in MongoDB: {e}")
