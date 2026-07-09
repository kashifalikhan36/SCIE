import json
from typing import Optional, List, Dict, Any

from database.redis import get_redis
from engine.behavior.schemas import ParticipantBehaviorState, BehaviorEvidence, BehaviorFeatures
from engine.behavior.config import behavior_config
from engine.behavior.constants import (
    REDIS_KEY_BEHAVIOR_STATE,
    REDIS_KEY_BEHAVIOR_TIMELINE,
    REDIS_KEY_MEETING_BEHAVIORS,
)
from engine.behavior.utils import now_ms
from engine.behavior.exceptions import BehaviorStateError
from engine.behavior.logger import logger, measure_latency


class BehaviorStateManager:
  """Manages live ParticipantBehaviorState in Azure Cache for Redis.

  Responsibilities:
  - Serialize and persist the latest behavior state for each participant.
  - Maintain a meeting-level set of tracked participant IDs (`REDIS_KEY_MEETING_BEHAVIORS`).
  - Provide O(1) live state retrieval by participant_id.
  """

  @measure_latency("state_manager.save_state")
  async def save_state(
      self,
      features: BehaviorFeatures,
      evidence: BehaviorEvidence,
      current_behavior: str = "idle"
  ) -> ParticipantBehaviorState:
    """Persist latest participant behavior state derived from features and evidence."""
    redis = await get_redis()

    # Determine current behavior state if not explicitly passed
    state_str = current_behavior
    if features.screen_share:
      state_str = "screen_sharing"
    elif evidence.speaking_ratio > 0.40 or (now_ms() - features.last_activity < 3000):
      state_str = "speaking"
    elif features.camera_on:
      state_str = "active"

    latest_metrics = {
        "speech_time": features.speech_time,
        "word_count": features.word_count,
        "turn_count": features.turn_count,
        "question_count": features.question_count,
        "interruptions": features.interruptions,
        "visible_time": features.visible_time,
        "camera_ratio": evidence.camera_ratio,
        "screen_share_ratio": evidence.screen_share_ratio,
    }

    state_obj = ParticipantBehaviorState(
        participant_id=features.participant_id,
        current_behavior=state_str,
        latest_metrics=latest_metrics,
        engagement_score=evidence.engagement_score,
        camera_status=features.camera_on,
        screen_share=features.screen_share,
        speaking_ratio=evidence.speaking_ratio,
        last_updated=now_ms()
    )

    if redis is None:
      logger.warning("BehaviorStateManager: Redis unavailable — state held in memory only.")
      return state_obj

    try:
      ttl = behavior_config.REDIS_STATE_TTL_SEC
      state_key = REDIS_KEY_BEHAVIOR_STATE.format(
          meeting_id=evidence.meeting_id,
          participant_id=features.participant_id
      )
      await redis.set(state_key, state_obj.model_dump_json(), ex=ttl)

      # Track participant ID in meeting behaviors set
      set_key = REDIS_KEY_MEETING_BEHAVIORS.format(meeting_id=evidence.meeting_id)
      await redis.sadd(set_key, features.participant_id)
      await redis.expire(set_key, ttl)

      logger.debug(f"Saved live behavior state to Redis for {features.participant_id}")
      return state_obj

    except Exception as exc:
      logger.error(f"Error saving behavior state to Redis for {features.participant_id}: {exc}")
      raise BehaviorStateError(f"Redis save_state failed: {exc}") from exc

  @measure_latency("state_manager.get_state")
  async def get_state(
      self, meeting_id: str, participant_id: str
  ) -> Optional[ParticipantBehaviorState]:
    """Fetch live behavior state from Redis for a participant."""
    redis = await get_redis()
    if redis is None:
      return None

    try:
      state_key = REDIS_KEY_BEHAVIOR_STATE.format(
          meeting_id=meeting_id, participant_id=participant_id
      )
      data = await redis.get(state_key)
      if not data:
        return None
      if isinstance(data, bytes):
        data = data.decode("utf-8")
      return ParticipantBehaviorState.model_validate_json(data)
    except Exception as exc:
      logger.error(f"Error fetching behavior state from Redis for {participant_id}: {exc}")
      return None

  async def get_all_participants(self, meeting_id: str) -> List[str]:
    """Retrieve all participant IDs currently tracked by the behavior engine for a meeting."""
    redis = await get_redis()
    if redis is None:
      return []

    try:
      set_key = REDIS_KEY_MEETING_BEHAVIORS.format(meeting_id=meeting_id)
      members = await redis.smembers(set_key)
      if not members:
        return []
      return [m.decode("utf-8") if isinstance(m, bytes) else str(m) for m in members]
    except Exception as exc:
      logger.error(f"Error fetching meeting behaviors set for {meeting_id}: {exc}")
      return []
