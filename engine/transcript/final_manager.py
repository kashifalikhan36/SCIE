import logging
from typing import List

from database.redis import get_redis
from engine.transcript.schemas import TranscriptChunk
from engine.transcript.config import transcript_config
from engine.transcript.constants import REDIS_KEY_FINAL_HISTORY, REDIS_KEY_FINALIZED_SET
from engine.transcript.partial_manager import PartialTranscriptManager
from engine.transcript.exceptions import FinalManagerError

logger = logging.getLogger("SCIE.transcript_engine.final_manager")


def _chunk_fingerprint(chunk: TranscriptChunk) -> str:
  """Returns a stable dedup fingerprint for a finalized chunk.

  Matches on speaker_id, start_time (1 dp), and timestamp window.
  Intentionally coarse to catch re-delivered final events from retried
  Audio Engine workers.
  """
  # Round start_time to 1 decimal place to absorb floating-point jitter
  rounded_start = round(chunk.start_time, 1)
  # Bucket timestamp into FINALIZE_DEDUP_WINDOW_MS windows
  window = chunk.timestamp // transcript_config.FINALIZE_DEDUP_WINDOW_MS
  return f"{chunk.speaker_id}|{rounded_start}|{window}"


class FinalTranscriptManager:
  """Archives finalized utterances and maintains their Redis history.

  Responsibilities
  ----------------
  - Wipe the corresponding partial cache key (via ``PartialTranscriptManager``).
  - Guard against double-archiving the same final event using a Redis Set
    that stores chunk fingerprints.
  - Append the finalized chunk to the speaker's Redis history list.
  - Trim the history list to ``HISTORY_MAX_SIZE`` to prevent unbounded growth
    in long meetings.
  - Retrieve the full finalized history on demand.
  - Clean up all Redis state for a finished meeting.

  Invariants
  ----------
  - A finalized chunk is **never** modified after archiving.
  - The history list remains chronologically ordered (append-only, RPUSH).
  """

  def __init__(self) -> None:
    self._partial_manager = PartialTranscriptManager()

  @staticmethod
  def _history_key(meeting_id: str, speaker_id: str) -> str:
    return REDIS_KEY_FINAL_HISTORY.format(
        meeting_id=meeting_id, speaker_id=speaker_id
    )

  @staticmethod
  def _finalized_set_key(meeting_id: str, speaker_id: str) -> str:
    return REDIS_KEY_FINALIZED_SET.format(
        meeting_id=meeting_id, speaker_id=speaker_id
    )

  async def finalize_utterance(
      self,
      meeting_id: str,
      chunk: TranscriptChunk,
  ) -> List[TranscriptChunk]:
    """Archives *chunk*, clears the partial, and returns the full history.

    Parameters
    ----------
    meeting_id:
        Meeting scope.
    chunk:
        A ``TranscriptChunk`` with ``is_final=True``.

    Returns
    -------
    List[TranscriptChunk]
        All finalized chunks for this speaker in the order they were archived.

    Raises
    ------
    FinalManagerError
        If the Redis operation fails unexpectedly.
    """
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("FinalManager: Redis unavailable — cannot archive finalized utterance.")
      return []

    speaker_id = chunk.speaker_id

    try:
      # ── 1. Deduplication guard ─────────────────────────────────────────
      fp          = _chunk_fingerprint(chunk)
      dedup_key   = self._finalized_set_key(meeting_id, speaker_id)
      already_archived = await redis_client.sismember(dedup_key, fp)

      if already_archived:
        logger.warning(
            f"FinalManager: Duplicate final event discarded — "
            f"speaker={speaker_id}, start={chunk.start_time:.2f}, fp={fp}"
        )
        # Return current history without re-archiving
        return await self.get_finalized_history(meeting_id, speaker_id)

      # ── 2. Mark as archived ────────────────────────────────────────────
      await redis_client.sadd(dedup_key, fp)
      # The dedup set can expire after the meeting is well over
      await redis_client.expire(dedup_key, transcript_config.REDIS_STATE_TTL_SEC)

      # ── 3. Clear the rolling partial ───────────────────────────────────
      await self._partial_manager.clear_partial(meeting_id, speaker_id)

      # ── 4. Append to ordered history list ─────────────────────────────
      history_key = self._history_key(meeting_id, speaker_id)
      await redis_client.rpush(history_key, chunk.model_dump_json())

      # ── 5. Trim history to configured maximum ─────────────────────────
      # LTRIM keeps items from index 0 to -(1) inclusive; trim from the left.
      max_idx = transcript_config.HISTORY_MAX_SIZE - 1
      await redis_client.ltrim(history_key, -transcript_config.HISTORY_MAX_SIZE, -1)

      logger.info(
          f"FinalManager: Archived final utterance — "
          f"speaker={speaker_id}, meeting={meeting_id}, "
          f"text='{chunk.text[:60]}'"
      )

      # ── 6. Return updated history ──────────────────────────────────────
      return await self.get_finalized_history(meeting_id, speaker_id)

    except FinalManagerError:
      raise
    except Exception as exc:
      raise FinalManagerError(
          f"Failed to process finalized utterance for speaker {speaker_id}: {exc}"
      ) from exc

  async def get_finalized_history(
      self,
      meeting_id: str,
      speaker_id: str,
  ) -> List[TranscriptChunk]:
    """Returns all archived finalized chunks for *speaker_id* in order."""
    redis_client = await get_redis()
    if not redis_client:
      return []
    try:
      history_key = self._history_key(meeting_id, speaker_id)
      items       = await redis_client.lrange(history_key, 0, -1)
      return [TranscriptChunk.model_validate_json(item) for item in items]
    except Exception as exc:
      logger.error(
          f"FinalManager: Failed to retrieve history for speaker={speaker_id}: {exc}"
      )
      return []

  async def clear_meeting_history(
      self,
      meeting_id: str,
      speaker_ids: List[str],
  ) -> None:
    """Removes all Redis state for a completed meeting session.

    Deletes history lists, dedup sets, and partial keys for every speaker.
    """
    redis_client = await get_redis()
    if not redis_client:
      return
    try:
      keys = []
      for sid in speaker_ids:
        keys.append(self._history_key(meeting_id, sid))
        keys.append(self._finalized_set_key(meeting_id, sid))
      if keys:
        await redis_client.delete(*keys)
      logger.info(
          f"FinalManager: Cleared {len(speaker_ids)} speaker histories "
          f"for meeting={meeting_id}"
      )
    except Exception as exc:
      logger.error(
          f"FinalManager: Failed to clean up meeting history for {meeting_id}: {exc}"
      )
