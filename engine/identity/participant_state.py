import json
import logging
from typing import Optional, List, Dict, Any

from database.redis import get_redis
from engine.identity.schemas import IdentityEvidence, ParticipantIdentityState
from engine.identity.config import identity_config
from engine.identity.constants import (
    REDIS_KEY_IDENTITY_STATE,
    REDIS_KEY_IDENTITY_PARTICIPANTS,
)
from engine.identity.utils import now_ms
from engine.identity.exceptions import IdentityStateError

logger = logging.getLogger("SCIE.identity_engine.participant_state")


class IdentityStateManager:
  """Manages live ParticipantIdentityState in Azure Cache for Redis.

  Responsibilities:
  - Serialize and persist the latest identity state for each participant.
  - Maintain a meeting-level set of tracked participant IDs.
  - Accumulate bounded history snapshots for incremental score tracking.
  - Apply confidence smoothing on temporary score dips.
  - Provide O(1) state retrieval by participant_id.
  """

  async def save_state(
      self,
      evidence: IdentityEvidence,
      existing_state: Optional[ParticipantIdentityState] = None,
  ) -> ParticipantIdentityState:
    """Persists the latest identity state to Redis derived from IdentityEvidence.

    Args:
        evidence: The IdentityEvidence emitted by the pipeline.
        existing_state: Previous state for history accumulation and smoothing.

    Returns:
        The updated ParticipantIdentityState.

    Raises:
        IdentityStateError: If the Redis write fails.
    """
    redis = await get_redis()
    state_obj = self._build_state(evidence, existing_state)

    if redis is None:
      logger.warning("IdentityStateManager: Redis unavailable — state held in memory only.")
      return state_obj

    try:
      ttl = identity_config.REDIS_STATE_TTL_SEC

      # 1. Write main state JSON
      state_key = REDIS_KEY_IDENTITY_STATE.format(
          meeting_id=evidence.meeting_id,
          participant_id=evidence.participant_id
      )
      await redis.set(state_key, state_obj.model_dump_json(), ex=ttl)

      # 2. Register participant in meeting set
      set_key = REDIS_KEY_IDENTITY_PARTICIPANTS.format(meeting_id=evidence.meeting_id)
      await redis.sadd(set_key, evidence.participant_id)
      await redis.expire(set_key, ttl)

      logger.info(
          f"IdentityStateManager: Synced state for {evidence.participant_id} in "
          f"meeting={evidence.meeting_id} (score={state_obj.identity_score:.4f})"
      )
      return state_obj

    except Exception as exc:
      raise IdentityStateError(
          f"Failed to save identity state for {evidence.participant_id}: {exc}"
      ) from exc

  async def get_state(
      self,
      meeting_id: str,
      participant_id: str,
  ) -> Optional[ParticipantIdentityState]:
    """Retrieves the latest identity state from Redis.

    Args:
        meeting_id: Meeting identifier.
        participant_id: Participant identifier.

    Returns:
        ParticipantIdentityState or None if not found / Redis unavailable.
    """
    redis = await get_redis()
    if redis is None:
      return None
    try:
      key = REDIS_KEY_IDENTITY_STATE.format(
          meeting_id=meeting_id, participant_id=participant_id
      )
      raw = await redis.get(key)
      if raw is None:
        return None
      text = raw if isinstance(raw, str) else raw.decode("utf-8")
      return ParticipantIdentityState.model_validate_json(text)
    except Exception as exc:
      logger.error(f"IdentityStateManager: Error fetching state for {participant_id}: {exc}")
      return None

  async def get_all_participants(self, meeting_id: str) -> List[str]:
    """Returns all participant IDs tracked by the identity engine for a meeting.

    Args:
        meeting_id: Meeting identifier.

    Returns:
        List of participant_id strings (may be empty).
    """
    redis = await get_redis()
    if redis is None:
      return []
    try:
      set_key = REDIS_KEY_IDENTITY_PARTICIPANTS.format(meeting_id=meeting_id)
      members = await redis.smembers(set_key)
      return [m if isinstance(m, str) else m.decode("utf-8") for m in members]
    except Exception as exc:
      logger.error(f"IdentityStateManager: Error fetching participants: {exc}")
      return []

  def _build_state(
      self,
      evidence: IdentityEvidence,
      existing_state: Optional[ParticipantIdentityState],
  ) -> ParticipantIdentityState:
    """Constructs a new ParticipantIdentityState from IdentityEvidence.

    Applies confidence smoothing: if the new confidence is lower than
    the previous, smooth with 70/30 weighting to handle transient dips.

    Args:
        evidence: Latest IdentityEvidence.
        existing_state: Previous state (for history and smoothing).

    Returns:
        New ParticipantIdentityState.
    """
    history = list(existing_state.history) if existing_state else []
    snapshot: Dict[str, Any] = {
        "timestamp": evidence.timestamp,
        "identity_score": evidence.overall_identity_score,
        "confidence": evidence.confidence,
        "email_score": evidence.email_score,
        "rapidfuzz_score": evidence.rapidfuzz_score,
        "semantic_score": evidence.semantic_score,
        "alias_score": evidence.alias_score,
        "metadata_score": evidence.metadata_score,
        "top_reasons": evidence.reasons[:5],
    }
    history.append(snapshot)

    # Trim history to max length
    if len(history) > identity_config.HISTORY_MAX_LENGTH:
      history = history[-identity_config.HISTORY_MAX_LENGTH:]

    # Confidence smoothing on dip
    prev_conf = existing_state.confidence if existing_state else 0.0
    new_conf = evidence.confidence
    if existing_state and prev_conf > new_conf and new_conf > 0.30:
      smoothed_conf = round((prev_conf * 0.70) + (new_conf * 0.30), 4)
    else:
      smoothed_conf = new_conf

    return ParticipantIdentityState(
        participant_id=evidence.participant_id,
        meeting_id=evidence.meeting_id,
        display_name=evidence.raw_display_name,
        normalized_name=evidence.normalized_participant_name,
        email=evidence.participant_email,
        identity_score=evidence.overall_identity_score,
        semantic_score=evidence.semantic_score,
        rapidfuzz_score=evidence.rapidfuzz_score,
        email_score=evidence.email_score,
        alias_score=evidence.alias_score,
        metadata_score=evidence.metadata_score,
        confidence=smoothed_conf,
        history=history,
        last_updated=evidence.timestamp,
    )
