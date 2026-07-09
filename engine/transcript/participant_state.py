import logging
from typing import Optional

from database.redis import get_redis
from engine.transcript.schemas import TranscriptEvidence, ParticipantTranscriptState
from engine.transcript.config import transcript_config
from engine.transcript.constants import REDIS_KEY_STATE
from engine.transcript.utils import compute_avg_wpm, now_ms

logger = logging.getLogger("SCIE.transcript_engine.participant_state")


class ParticipantTranscriptStateManager:
  """Manages live ``ParticipantTranscriptState`` cached in Azure Cache for Redis.

  The state blob is the single source of truth for the *current* transcript
  state of a speaker during an active meeting.  It is written after every
  evidence object (partial and final) and expires automatically via TTL.

  Downstream dashboards and the Behavior Engine should read from this key
  for real-time transcript status rather than querying MongoDB.
  """

  @staticmethod
  def _key(meeting_id: str, speaker_id: str) -> str:
    return REDIS_KEY_STATE.format(meeting_id=meeting_id, speaker_id=speaker_id)

  async def get_state(
      self,
      meeting_id: str,
      speaker_id: str,
  ) -> Optional[ParticipantTranscriptState]:
    """Retrieves the current transcript state for *speaker_id* from Redis.

    Returns ``None`` if the key does not exist or Redis is unavailable.
    """
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("ParticipantTranscriptStateManager: Redis unavailable — cannot read state.")
      return None
    try:
      data = await redis_client.get(self._key(meeting_id, speaker_id))
      if data:
        return ParticipantTranscriptState.model_validate_json(data)
      return None
    except Exception as exc:
      logger.error(
          f"ParticipantTranscriptStateManager: Failed to read state for "
          f"speaker={speaker_id}: {exc}"
      )
      return None

  async def update_state(
      self,
      meeting_id: str,
      evidence: TranscriptEvidence,
  ) -> Optional[ParticipantTranscriptState]:
    """Merges *evidence* into the speaker's Redis state and persists it.

    Handles both partial (rolling) and final evidence correctly:

    - **Partial**: updates ``latest_partial``, preserves ``latest_final``
      and cumulative stats unchanged.
    - **Final**: appends to ``conversation_history``, clears
      ``latest_partial``, increments ``word_count`` / ``speaking_duration``
      / ``avg_wpm``.

    The Redis key is written with ``REDIS_STATE_TTL_SEC`` expiry so that
    state for completed meetings is automatically reclaimed.

    Returns
    -------
    Optional[ParticipantTranscriptState]
        The updated state, or ``None`` if Redis is unavailable.
    """
    redis_client = await get_redis()
    if not redis_client:
      logger.warning(
          "ParticipantTranscriptStateManager: Redis unavailable — skipping state update."
      )
      return None

    speaker_id = evidence.speaker_id

    try:
      current = await self.get_state(meeting_id, speaker_id)
      now     = now_ms()

      if current:
        updated = self._merge_state(current, evidence, now)
      else:
        updated = self._build_new_state(evidence, now)

      key = self._key(meeting_id, speaker_id)
      await redis_client.set(
          key,
          updated.model_dump_json(),
          ex=transcript_config.REDIS_STATE_TTL_SEC,
      )

      logger.info(
          f"ParticipantTranscriptStateManager: Updated state — "
          f"speaker={speaker_id}, meeting={meeting_id}, "
          f"is_final={evidence.is_final}, "
          f"words={updated.word_count}, duration={updated.speaking_duration:.1f}s"
      )
      return updated

    except Exception as exc:
      logger.error(
          f"ParticipantTranscriptStateManager: Failed to update state for "
          f"speaker={speaker_id}: {exc}"
      )
      return None

  # ── Private helpers ───────────────────────────────────────────────────────

  @staticmethod
  def _build_new_state(
      evidence: TranscriptEvidence,
      now_ms_val: int,
  ) -> ParticipantTranscriptState:
    """Creates a brand-new state from the first evidence for this speaker."""
    if evidence.is_final:
      return ParticipantTranscriptState(
          speaker_id=evidence.speaker_id,
          latest_partial=None,
          latest_final=evidence.text,
          conversation_history=[evidence.text],
          last_updated=now_ms_val,
          word_count=evidence.word_count,
          speaking_duration=evidence.duration,
          avg_wpm=evidence.avg_wpm,
      )
    else:
      return ParticipantTranscriptState(
          speaker_id=evidence.speaker_id,
          latest_partial=evidence.text,
          latest_final=None,
          conversation_history=[],
          last_updated=now_ms_val,
          word_count=0,
          speaking_duration=0.0,
          avg_wpm=0.0,
      )

  @staticmethod
  def _merge_state(
      current: ParticipantTranscriptState,
      evidence: TranscriptEvidence,
      now_ms_val: int,
  ) -> ParticipantTranscriptState:
    """Merges incoming evidence into an existing state object."""
    if evidence.is_final:
      history = list(current.conversation_history)
      history.append(evidence.text)
      # Cap history size to prevent Redis bloat in very long meetings
      if len(history) > transcript_config.HISTORY_MAX_SIZE:
        history = history[-transcript_config.HISTORY_MAX_SIZE:]

      new_word_count        = current.word_count + evidence.word_count
      new_speaking_duration = current.speaking_duration + evidence.duration
      new_avg_wpm           = compute_avg_wpm(new_word_count, new_speaking_duration)

      return ParticipantTranscriptState(
          speaker_id=evidence.speaker_id,
          latest_partial=None,          # Final arrival clears partial
          latest_final=evidence.text,
          conversation_history=history,
          last_updated=now_ms_val,
          word_count=new_word_count,
          speaking_duration=round(new_speaking_duration, 3),
          avg_wpm=round(new_avg_wpm, 2),
      )
    else:
      # Partial update — only refresh latest_partial; keep all finals intact
      return ParticipantTranscriptState(
          speaker_id=evidence.speaker_id,
          latest_partial=evidence.text,
          latest_final=current.latest_final,
          conversation_history=current.conversation_history,
          last_updated=now_ms_val,
          word_count=current.word_count,
          speaking_duration=current.speaking_duration,
          avg_wpm=current.avg_wpm,
      )
