"""
Live Participant Conversation Reasoning State Manager (Redis).

Responsibilities:
- Persist ParticipantConversationState in Azure Cache for Redis.
- Ensure sub-millisecond retrieval of the latest semantic reasoning profiles per speaker.
- Track all active speakers evaluated within a meeting.
"""
import json
from typing import List, Optional
from database.redis import get_redis
from engine.conversation.config import conversation_config
from engine.conversation.constants import REDIS_KEY_CONVERSATION_STATE, REDIS_KEY_MEETING_SPEAKERS
from engine.conversation.schemas import ParticipantConversationState
from engine.conversation.exceptions import ConversationStateError
from engine.conversation.logger import logger


class ConversationStateManager:
  """Async Redis manager for live participant conversation reasoning states."""

  def __init__(self):
    self._ttl = conversation_config.REDIS_STATE_TTL_SEC

  async def save_state(self, state: ParticipantConversationState) -> ParticipantConversationState:
    """Save or overwrite live conversation reasoning state in Redis with configured TTL."""
    try:
      redis = await get_redis()
      if redis is None:
        logger.warning(f"StateManager: Redis unavailable when saving state for {state.speaker_id}.")
        return state

      key = REDIS_KEY_CONVERSATION_STATE.format(meeting_id=state.meeting_id, speaker_id=state.speaker_id)
      await redis.set(key, state.model_dump_json(), ex=self._ttl)

      # Track speaker ID in meeting set
      set_key = REDIS_KEY_MEETING_SPEAKERS.format(meeting_id=state.meeting_id)
      await redis.sadd(set_key, state.speaker_id)
      await redis.expire(set_key, self._ttl)

      logger.debug(f"Saved live conversation reasoning state to Redis for {state.speaker_id}")
      return state
    except Exception as exc:
      logger.error(f"StateManager: Failed to save state to Redis for {state.speaker_id}: {exc}")
      raise ConversationStateError(f"Failed to save state to Redis: {exc}") from exc

  async def get_state(self, meeting_id: str, speaker_id: str) -> Optional[ParticipantConversationState]:
    """Retrieve live participant conversation reasoning state from Redis."""
    try:
      redis = await get_redis()
      if redis is None:
        return None

      key = REDIS_KEY_CONVERSATION_STATE.format(meeting_id=meeting_id, speaker_id=speaker_id)
      raw = await redis.get(key)
      if raw:
        return ParticipantConversationState.model_validate_json(raw)
      return None
    except Exception as exc:
      logger.warning(f"StateManager: Failed to get state for {speaker_id}: {exc}")
      return None

  async def get_all_speakers(self, meeting_id: str) -> List[str]:
    """Retrieve all speaker IDs tracked for a meeting from Redis."""
    try:
      redis = await get_redis()
      if redis is None:
        return []

      set_key = REDIS_KEY_MEETING_SPEAKERS.format(meeting_id=meeting_id)
      members = await redis.smembers(set_key)
      return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members]
    except Exception as exc:
      logger.warning(f"StateManager: Failed to get speakers for meeting {meeting_id}: {exc}")
      return []
