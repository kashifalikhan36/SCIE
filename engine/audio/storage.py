import logging
from typing import Dict, Any, List
from database.mongodb import get_mongo_db
from engine.audio.schemas import VoiceEvidence
from engine.audio.constants import (
    MONGO_MEETINGS_COL,
    MONGO_SEGMENTS_COL,
    MONGO_TRANSCRIPTS_COL,
    MONGO_EMBEDDINGS_COL,
    MONGO_EVIDENCE_COL
)
from engine.audio.exceptions import StorageError

logger = logging.getLogger("SCIE.audio_engine.storage")

class AudioStorageManager:
  """Handles MongoDB persistence for all historical audio engine artifacts."""

  def __init__(self):
    # Retrieve DB handler lazily on use
    pass

  async def save_meeting_info(self, meeting_id: str, metadata: Dict[str, Any]):
    """Persists meeting metadata if it doesn't already exist or updates it."""
    db = get_mongo_db()
    if db is None:
      logger.warning("MongoDB unavailable; skipping meeting info save.")
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

  async def save_audio_segment(self, meeting_id: str, segment_data: Dict[str, Any]):
    """Saves info about a parsed audio segment to historical collection."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_SEGMENTS_COL]
      await col.insert_one({**segment_data, "meeting_id": meeting_id})
      logger.debug(f"Saved audio segment record in MongoDB.")
    except Exception as e:
      logger.error(f"Failed to save audio segment in MongoDB: {e}")

  async def save_transcript_segment(self, meeting_id: str, speaker_id: str, text: str, start: float, end: float, timestamp: int):
    """Saves raw transcript chunks with timestamps and speaker identifiers."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_TRANSCRIPTS_COL]
      doc = {
          "meeting_id": meeting_id,
          "speaker_id": speaker_id,
          "text": text,
          "start": start,
          "end": end,
          "timestamp": timestamp
      }
      await col.insert_one(doc)
      logger.debug(f"Saved transcript segment in MongoDB for speaker {speaker_id}")
    except Exception as e:
      logger.error(f"Failed to save transcript in MongoDB: {e}")

  async def save_speaker_embedding(self, meeting_id: str, speaker_id: str, embedding: List[float], timestamp: int):
    """Saves a speaker embedding vector to MongoDB, avoiding duplication by unique speaker_id."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_EMBEDDINGS_COL]
      # Prevent duplicates by using speaker_id as the primary filter key
      await col.update_one(
          {"meeting_id": meeting_id, "speaker_id": speaker_id},
          {"$setOnInsert": {
              "meeting_id": meeting_id,
              "speaker_id": speaker_id,
              "embedding": embedding,
              "created_at": timestamp
          }},
          upsert=True
      )
      logger.debug(f"Saved unique speaker embedding in MongoDB for speaker {speaker_id}")
    except Exception as e:
      logger.error(f"Failed to save speaker embedding in MongoDB: {e}")

  async def save_voice_evidence(self, evidence: VoiceEvidence):
    """Saves final assembled VoiceEvidence objects to MongoDB."""
    db = get_mongo_db()
    if db is None:
      return

    try:
      col = db[MONGO_EVIDENCE_COL]
      doc = evidence.model_dump()
      await col.insert_one(doc)
      logger.info(f"Persisted VoiceEvidence record in MongoDB for speaker {evidence.speaker_id}")
    except Exception as e:
      logger.error(f"Failed to save voice evidence in MongoDB: {e}")
