import json
import logging
import time
from typing import Optional
from database.redis import get_redis
from engine.video.schemas import VisualEvidence, ParticipantVisualState

logger = logging.getLogger("SCIE.video_engine.participant_state")

class ParticipantVisualStateManager:
  """Manages the live ParticipantVisualState cached inside Azure Cache for Redis."""

  @staticmethod
  def _get_redis_key(meeting_id: str, track_id: str) -> str:
    return f"scie:meeting:{meeting_id}:video:participant:{track_id}:state"

  async def get_state(self, meeting_id: str, track_id: str) -> Optional[ParticipantVisualState]:
    """Retrieves the latest participant visual state from Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("Redis client unavailable; cannot retrieve visual participant state.")
      return None

    try:
      key = self._get_redis_key(meeting_id, track_id)
      data_json = await redis_client.get(key)
      if data_json:
        return ParticipantVisualState.model_validate_json(data_json)
      return None
    except Exception as e:
      logger.error(f"Failed to retrieve visual participant state from Redis: {e}")
      return None

  async def update_state(self, meeting_id: str, evidence: VisualEvidence) -> Optional[ParticipantVisualState]:
    """Updates and saves the latest participant visual state in Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("Redis client unavailable; skipping visual state update.")
      return None

    try:
      track_id = evidence.track_id
      key = self._get_redis_key(meeting_id, track_id)
      
      updated_state = ParticipantVisualState(
          track_id=track_id,
          latest_embedding=evidence.face_embedding,
          latest_similarity=evidence.face_similarity,
          last_seen=evidence.timestamp,
          face_visible=evidence.visibility,
          tracking_confidence=evidence.tracking_confidence,
          recognition_confidence=evidence.recognition_confidence,
          timestamp=evidence.timestamp
      )

      # Save state to Redis
      await redis_client.set(key, updated_state.model_dump_json())
      logger.info(f"Updated live ParticipantVisualState in Redis for {track_id} in meeting {meeting_id}")
      return updated_state

    except Exception as e:
      logger.error(f"Failed to update visual participant state in Redis: {e}")
      return None
