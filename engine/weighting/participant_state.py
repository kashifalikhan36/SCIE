"""
Participant State Client for the Dynamic Weighting Engine.

Retrieves and caches the latest upstream ``ParticipantState`` from Redis or in-memory fallback
to understand current meeting context (camera_on, mic_on, screen_share, etc.).

(`engine/weighting/participant_state.py`)
"""
import json
from typing import Optional, Dict
from engine.weighting.schemas import UpstreamParticipantState
from engine.weighting.constants import REDIS_KEY_PARTICIPANT_STATE_UPSTREAM
from engine.weighting.logger import logger, measure_latency

try:
  from backend.config import get_redis
except ImportError:
  try:
    from config import get_redis
  except ImportError:
    async def get_redis():
      return None


class ParticipantStateManager:
  """Manages retrieval and caching of upstream participant context."""

  def __init__(self):
    self._memory_cache: Dict[str, UpstreamParticipantState] = {}

  @measure_latency("weighting.get_participant_state")
  async def get_participant_state(self, meeting_id: str, participant_id: str) -> UpstreamParticipantState:
    """Retrieve participant meeting context state from Redis or local cache."""
    cache_key = f"{meeting_id}:{participant_id}"
    redis_client = await get_redis()
    if redis_client:
      key = REDIS_KEY_PARTICIPANT_STATE_UPSTREAM.format(
          meeting_id=meeting_id, participant_id=participant_id
      )
      try:
        raw = await redis_client.get(key)
        if raw:
          if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
          data = json.loads(raw)
          state = UpstreamParticipantState(**data)
          self._memory_cache[cache_key] = state
          return state
      except Exception as e:
        logger.warning(f"Failed to fetch participant state from Redis for {key}: {e}")

    # Fallback to local cache or defaults
    if cache_key in self._memory_cache:
      return self._memory_cache[cache_key]

    default_state = UpstreamParticipantState(
        participant_id=participant_id,
        meeting_id=meeting_id,
        camera_on=True,
        mic_on=True,
        screen_share=False,
        face_visible=True,
        voice_detected=True,
        transcript_available=True
    )
    self._memory_cache[cache_key] = default_state
    return default_state

  async def save_participant_state_fallback(self, state: UpstreamParticipantState):
    """Save participant state to Redis and local fallback (used for tests or upstream mocking)."""
    cache_key = f"{state.meeting_id}:{state.participant_id}"
    self._memory_cache[cache_key] = state
    redis_client = await get_redis()
    if redis_client:
      key = REDIS_KEY_PARTICIPANT_STATE_UPSTREAM.format(
          meeting_id=state.meeting_id, participant_id=state.participant_id
      )
      try:
        await redis_client.set(key, state.model_dump_json(), ex=7200)
      except Exception as e:
        logger.warning(f"Failed to persist fallback state to Redis: {e}")
