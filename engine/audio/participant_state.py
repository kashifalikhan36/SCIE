import json
import logging
import time
from typing import Optional, List, Dict, Any
from database.redis import get_redis
from engine.audio.schemas import VoiceEvidence, ParticipantAudioState

logger = logging.getLogger("SCIE.audio_engine.participant_state")

class ParticipantStateManager:
  """Manages the live ParticipantAudioState stored inside Azure Cache for Redis."""

  @staticmethod
  def _get_redis_key(meeting_id: str, speaker_id: str) -> str:
    return f"scie:meeting:{meeting_id}:participant:{speaker_id}:state"

  async def get_state(self, meeting_id: str, speaker_id: str) -> Optional[ParticipantAudioState]:
    """Retrieves the current participant audio state from Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("Redis client unavailable; cannot retrieve participant state.")
      return None

    try:
      key = self._get_redis_key(meeting_id, speaker_id)
      data_json = await redis_client.get(key)
      if data_json:
        return ParticipantAudioState.model_validate_json(data_json)
      return None
    except Exception as e:
      logger.error(f"Failed to retrieve participant state from Redis: {e}")
      return None

  async def update_state(self, meeting_id: str, evidence: VoiceEvidence) -> Optional[ParticipantAudioState]:
    """Updates and merges incoming VoiceEvidence into the participant's Redis state."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("Redis client unavailable; skipping participant state update.")
      return None

    try:
      speaker_id = evidence.speaker_id
      key = self._get_redis_key(meeting_id, speaker_id)
      
      # 1. Fetch current state from Redis (if any exists)
      current_state = await self.get_state(meeting_id, speaker_id)
      
      now_ms = int(time.time() * 1000)
      
      # Helper segment structure
      new_segment = {
          "start": evidence.speech_start,
          "end": evidence.speech_end,
          "duration": evidence.speech_duration,
          "timestamp": evidence.timestamp
      }

      if current_state:
        # Merge states
        merged_segments = current_state.speech_segments
        merged_segments.append(new_segment)
        
        # Keep segments list under a reasonable size to prevent Redis bloat (e.g. last 50 segments)
        if len(merged_segments) > 50:
          merged_segments = merged_segments[-50:]

        updated_state = ParticipantAudioState(
            speaker_id=speaker_id,
            voice_embedding=evidence.voice_embedding, # Keep the latest embedding
            last_transcript=evidence.transcript or current_state.last_transcript,
            language=evidence.language or current_state.language,
            last_seen=now_ms,
            speech_duration=current_state.speech_duration + evidence.speech_duration,
            speech_segments=merged_segments,
            recognition_score=(current_state.recognition_score + evidence.speaker_similarity) / 2.0,
            last_updated=now_ms
        )
      else:
        # Create new state
        updated_state = ParticipantAudioState(
            speaker_id=speaker_id,
            voice_embedding=evidence.voice_embedding,
            last_transcript=evidence.transcript,
            language=evidence.language,
            last_seen=now_ms,
            speech_duration=evidence.speech_duration,
            speech_segments=[new_segment],
            recognition_score=evidence.speaker_similarity,
            last_updated=now_ms
        )

      # 2. Save state to Redis
      await redis_client.set(key, updated_state.model_dump_json())
      logger.info(f"Updated live ParticipantAudioState in Redis for {speaker_id} in meeting {meeting_id}")
      return updated_state

    except Exception as e:
      logger.error(f"Failed to update participant state in Redis: {e}")
      return None
