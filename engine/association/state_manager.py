import json
import logging
from typing import Optional, List, Dict, Any

from database.redis import get_redis
from engine.association.schemas import ParticipantIdentity, ParticipantIdentityState
from engine.association.config import association_config
from engine.association.constants import (
    REDIS_KEY_PARTICIPANT_STATE,
    REDIS_KEY_MEETING_PARTICIPANTS,
    REDIS_KEY_TRACK_MAP,
    REDIS_KEY_SPEAKER_MAP,
)
from engine.association.exceptions import StateManagementError

logger = logging.getLogger("SCIE.association_engine.state_manager")


class AssociationStateManager:
  """Manages live ParticipantIdentityState cached in Azure Cache for Redis.

  Maintains synchronization across distributed worker instances and maintains
  O(1) reverse lookup maps from track_id and speaker_id to participant_id.
  Updates confidence incrementally as additional signals align over time.
  """

  async def get_state(
      self,
      meeting_id: str,
      participant_id: str,
  ) -> Optional[ParticipantIdentityState]:
    """Retrieves the live ParticipantIdentityState for a participant from Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("AssociationStateManager: Redis unavailable — cannot fetch state.")
      return None

    try:
      key = REDIS_KEY_PARTICIPANT_STATE.format(meeting_id=meeting_id, participant_id=participant_id)
      data = await redis_client.get(key)
      if not data:
        return None
      raw_json = data if isinstance(data, str) else data.decode("utf-8")
      return ParticipantIdentityState.model_validate_json(raw_json)
    except Exception as exc:
      logger.error(f"AssociationStateManager: Error fetching state for {participant_id}: {exc}")
      return None

  async def lookup_by_track_id(self, meeting_id: str, track_id: str) -> Optional[str]:
    """Resolves a track_id to its currently associated participant_id in O(1) time."""
    redis_client = await get_redis()
    if not redis_client or not track_id:
      return None
    try:
      key = REDIS_KEY_TRACK_MAP.format(meeting_id=meeting_id, track_id=track_id)
      pid = await redis_client.get(key)
      return (pid if isinstance(pid, str) else pid.decode("utf-8")) if pid else None
    except Exception as exc:
      logger.error(f"AssociationStateManager: Error looking up track {track_id}: {exc}")
      return None

  async def lookup_by_speaker_id(self, meeting_id: str, speaker_id: str) -> Optional[str]:
    """Resolves a speaker_id to its currently associated participant_id in O(1) time."""
    redis_client = await get_redis()
    if not redis_client or not speaker_id:
      return None
    try:
      key = REDIS_KEY_SPEAKER_MAP.format(meeting_id=meeting_id, speaker_id=speaker_id)
      pid = await redis_client.get(key)
      return (pid if isinstance(pid, str) else pid.decode("utf-8")) if pid else None
    except Exception as exc:
      logger.error(f"AssociationStateManager: Error looking up speaker {speaker_id}: {exc}")
      return None

  async def save_state(
      self,
      meeting_id: str,
      identity: ParticipantIdentity,
      existing_state: Optional[ParticipantIdentityState] = None,
  ) -> ParticipantIdentityState:
    """Updates and persists the live ParticipantIdentityState to Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("AssociationStateManager: Redis unavailable — building state in-memory only.")
      return self._build_state_obj(identity, existing_state)

    try:
      state_obj = self._build_state_obj(identity, existing_state)
      ttl = association_config.REDIS_STATE_TTL_SEC

      # 1. Save main participant state JSON
      state_key = REDIS_KEY_PARTICIPANT_STATE.format(
          meeting_id=meeting_id, participant_id=identity.participant_id
      )
      await redis_client.set(state_key, state_obj.model_dump_json(), ex=ttl)

      # 2. Add participant_id to the meeting's set of active participants
      set_key = REDIS_KEY_MEETING_PARTICIPANTS.format(meeting_id=meeting_id)
      await redis_client.sadd(set_key, identity.participant_id)
      await redis_client.expire(set_key, ttl)

      # 3. Update reverse lookup index map for track_id if assigned
      if identity.track_id:
        track_key = REDIS_KEY_TRACK_MAP.format(meeting_id=meeting_id, track_id=identity.track_id)
        await redis_client.set(track_key, identity.participant_id, ex=ttl)

      # 4. Update reverse lookup index map for speaker_id if assigned
      if identity.speaker_id:
        speaker_key = REDIS_KEY_SPEAKER_MAP.format(meeting_id=meeting_id, speaker_id=identity.speaker_id)
        await redis_client.set(speaker_key, identity.participant_id, ex=ttl)

      logger.info(
          f"AssociationStateManager: Synchronized state for {identity.participant_id} "
          f"(name={state_obj.display_name}, conf={state_obj.association_confidence:.4f})"
      )
      return state_obj

    except Exception as exc:
      raise StateManagementError(
          f"Failed to save state to Redis for participant {identity.participant_id}: {exc}"
      ) from exc

  def _build_state_obj(
      self,
      identity: ParticipantIdentity,
      existing_state: Optional[ParticipantIdentityState] = None,
  ) -> ParticipantIdentityState:
    """Helper constructing the ParticipantIdentityState preserving historical snapshots."""
    history = existing_state.history if existing_state else []
    # Append snapshot to history
    snapshot = {
        "timestamp": identity.timestamp,
        "score": identity.association_score,
        "confidence": identity.association_confidence,
        "track_id": identity.track_id,
        "speaker_id": identity.speaker_id,
        "reasons": identity.reasons[:5]  # Keep top 5 reasons to bound history size
    }
    history.append(snapshot)

    # Trim history if exceeding HISTORY_MAX_LENGTH
    if len(history) > association_config.HISTORY_MAX_LENGTH:
      history = history[-association_config.HISTORY_MAX_LENGTH:]

    # Incremental confidence update smoothing: if confidence increased, adopt immediately;
    # if dipped slightly due to temporary occlusions, maintain high-water mark or average.
    prev_conf = existing_state.association_confidence if existing_state else 0.0
    new_conf = identity.association_confidence
    if existing_state and prev_conf > new_conf and new_conf > 0.40:
      # Smooth minor temporary confidence dips across multi-modal noise
      smoothed_conf = round((prev_conf * 0.70) + (new_conf * 0.30), 4)
    else:
      smoothed_conf = new_conf

    return ParticipantIdentityState(
        participant_id=identity.participant_id,
        track_id=identity.track_id,
        speaker_id=identity.speaker_id,
        display_name=identity.display_name,
        email=identity.email,
        association_score=identity.association_score,
        association_confidence=smoothed_conf,
        history=history,
        last_updated=identity.timestamp
    )

  async def get_all_meeting_participants(self, meeting_id: str) -> List[str]:
    """Returns list of all participant_ids currently tracked in the meeting."""
    redis_client = await get_redis()
    if not redis_client:
      return []
    try:
      set_key = REDIS_KEY_MEETING_PARTICIPANTS.format(meeting_id=meeting_id)
      members = await redis_client.smembers(set_key)
      return [m if isinstance(m, str) else m.decode("utf-8") for m in members]
    except Exception as exc:
      logger.error(f"AssociationStateManager: Error fetching participants for meeting {meeting_id}: {exc}")
      return []
