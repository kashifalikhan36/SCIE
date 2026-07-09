import logging
from database.redis import get_redis
from engine.transcript.config import transcript_config
from engine.transcript.constants import REDIS_KEY_PARTIAL
from engine.transcript.utils import merge_partial_texts
from engine.transcript.exceptions import PartialManagerError

logger = logging.getLogger("SCIE.transcript_engine.partial_manager")


class PartialTranscriptManager:
  """Manages rolling / incomplete transcript text updates in Redis.

  Streaming ASR (Whisper) delivers progressively longer versions of the
  same utterance until a final segment is emitted.  This manager stores
  only the *latest* rolling text per speaker, replacing earlier versions
  instead of appending them.

  All Redis keys are written with a TTL so that stale partials from
  speakers who disconnect mid-utterance are automatically cleaned up.
  """

  @staticmethod
  def _key(meeting_id: str, speaker_id: str) -> str:
    return REDIS_KEY_PARTIAL.format(meeting_id=meeting_id, speaker_id=speaker_id)

  async def update_partial(
      self,
      meeting_id: str,
      speaker_id: str,
      text: str,
  ) -> str:
    """Replaces the active rolling partial text for a speaker.

    The Redis key is set with ``REDIS_PARTIAL_TTL_SEC`` expiry so orphaned
    partials (e.g. from disconnected speakers) are automatically reclaimed.

    Parameters
    ----------
    meeting_id, speaker_id:
        Identifiers scoping the partial key.
    text:
        The new (potentially longer) rolling text from the latest Whisper
        streaming chunk.

    Returns
    -------
    str
        The text that was persisted (after merge logic).

    Raises
    ------
    PartialManagerError
        If the Redis write fails.
    """
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("PartialManager: Redis unavailable — skipping partial update.")
      return text

    try:
      key = self._key(meeting_id, speaker_id)
      await redis_client.set(
          key,
          text,
          ex=transcript_config.REDIS_PARTIAL_TTL_SEC,
      )
      logger.debug(
          f"PartialManager: Updated partial for speaker={speaker_id} "
          f"(meeting={meeting_id}): '{text[:60]}'"
      )
      return text
    except Exception as exc:
      raise PartialManagerError(
          f"Failed to update partial transcript in Redis: {exc}"
      ) from exc

  async def merge_and_update_partial(
      self,
      meeting_id: str,
      speaker_id: str,
      new_text: str,
  ) -> str:
    """Fetches the current partial, merges it with *new_text*, and persists.

    Uses ``merge_partial_texts`` to always keep the semantically fuller
    version — preventing regressions when Whisper occasionally produces a
    shorter beam-search result.

    Returns
    -------
    str
        The merged text that was persisted.
    """
    current = await self.get_partial(meeting_id, speaker_id)
    merged  = merge_partial_texts(current, new_text)
    return await self.update_partial(meeting_id, speaker_id, merged)

  async def get_partial(self, meeting_id: str, speaker_id: str) -> str:
    """Returns the current rolling partial text, or an empty string."""
    redis_client = await get_redis()
    if not redis_client:
      return ""
    try:
      key  = self._key(meeting_id, speaker_id)
      data = await redis_client.get(key)
      if data is None:
        return ""
      return data if isinstance(data, str) else data.decode("utf-8")
    except Exception as exc:
      logger.error(f"PartialManager: Failed to fetch partial from Redis: {exc}")
      return ""

  async def clear_partial(self, meeting_id: str, speaker_id: str) -> None:
    """Deletes the partial cache key once a finalized chunk arrives.

    Called by ``FinalTranscriptManager`` after archiving the final segment.
    """
    redis_client = await get_redis()
    if not redis_client:
      return
    try:
      key = self._key(meeting_id, speaker_id)
      await redis_client.delete(key)
      logger.debug(
          f"PartialManager: Cleared partial key for speaker={speaker_id} "
          f"(meeting={meeting_id})"
      )
    except Exception as exc:
      logger.error(f"PartialManager: Failed to clear partial key in Redis: {exc}")
