import hashlib
import logging
from typing import Dict, List, Optional, Set, Tuple

from engine.transcript.schemas import TranscriptChunk
from engine.transcript.config import transcript_config

logger = logging.getLogger("SCIE.transcript_engine.buffer")


def _chunk_fingerprint(chunk: TranscriptChunk) -> str:
  """Returns a stable fingerprint for deduplication.

  The fingerprint is derived from speaker_id, rounded start_time
  (1 decimal place), and a 12-char MD5 of the normalised text body.
  This is intentionally coarse enough to catch near-duplicates caused
  by micro-second timestamp differences in re-deliveries.
  """
  text_hash = hashlib.md5(chunk.text.strip().lower().encode()).hexdigest()[:12]
  return f"{chunk.speaker_id}|{round(chunk.start_time, 1)}|{text_hash}"


class TranscriptBuffer:
  """Intelligent streaming buffer for per-meeting transcript chunks.

  Responsibilities
  ----------------
  - Buffer partial and final chunks in chronological order.
  - Detect and discard exact and near-duplicate chunks using a per-meeting
    fingerprint set.
  - Prevent memory growth in long meetings by capping buffer size and
    evicting *partial* (non-final) chunks first; finalized chunks are
    protected from eviction until they have been processed.
  - Expose ordered views and a cleanup hook for session teardown.

  Thread safety
  -------------
  All mutations are synchronous.  The async worker that calls this buffer
  runs on a single-threaded asyncio event loop so no locking is needed.
  """

  def __init__(self) -> None:
    # Per-meeting ordered chunk list
    self._buffers: Dict[str, List[TranscriptChunk]] = {}
    # Per-meeting fingerprint set for O(1) duplicate detection
    self._seen: Dict[str, Set[str]] = {}
    # Count of finalized chunks per meeting (protected from eviction)
    self._finalized_counts: Dict[str, int] = {}

  # ── Public API ────────────────────────────────────────────────────────────

  def add_chunk(self, chunk: TranscriptChunk) -> List[TranscriptChunk]:
    """Inserts *chunk* into the meeting buffer in chronological order.

    Duplicate chunks (same speaker + time range + text) are silently
    discarded.  The buffer is trimmed to ``BUFFER_MAX_SIZE`` by evicting
    the oldest *partial* chunk when full.

    Returns
    -------
    List[TranscriptChunk]
        The current ordered buffer for the meeting (after insertion).
    """
    mid = chunk.meeting_id
    self._ensure_meeting(mid)

    # Deduplication check
    fp = _chunk_fingerprint(chunk)
    if fp in self._seen[mid]:
      logger.debug(
          f"Buffer: Duplicate chunk discarded — speaker={chunk.speaker_id}, "
          f"start={chunk.start_time:.2f}"
      )
      return self._buffers[mid]

    self._seen[mid].add(fp)
    buf = self._buffers[mid]
    buf.append(chunk)

    # Maintain chronological order after each insert
    buf.sort(key=lambda c: c.start_time)

    if chunk.is_final:
      self._finalized_counts[mid] = self._finalized_counts.get(mid, 0) + 1

    # Trim buffer if over capacity — only evict partial chunks to protect finals
    self._trim_buffer(mid)

    logger.debug(
        f"Buffer: Accepted chunk for meeting={mid}, "
        f"speaker={chunk.speaker_id}, is_final={chunk.is_final}, "
        f"buffer_size={len(buf)}"
    )
    return buf

  def get_ordered_chunks(self, meeting_id: str) -> List[TranscriptChunk]:
    """Returns the full chronologically ordered buffer for *meeting_id*."""
    return list(self._buffers.get(meeting_id, []))

  def get_finalized_chunks(self, meeting_id: str) -> List[TranscriptChunk]:
    """Returns only the finalized (immutable) chunks for *meeting_id*."""
    return [c for c in self._buffers.get(meeting_id, []) if c.is_final]

  def clear_meeting(self, meeting_id: str) -> None:
    """Removes all buffer state for a finished meeting session."""
    self._buffers.pop(meeting_id, None)
    self._seen.pop(meeting_id, None)
    self._finalized_counts.pop(meeting_id, None)
    logger.debug(f"Buffer: Cleared all state for meeting={meeting_id}")

  def get_and_clear_meeting(self, meeting_id: str) -> List[TranscriptChunk]:
    """Atomically returns all chunks and clears the meeting buffer.

    Useful during session teardown to drain remaining unprocessed data
    before cleanup.
    """
    chunks = self.get_ordered_chunks(meeting_id)
    self.clear_meeting(meeting_id)
    return chunks

  # ── Private helpers ───────────────────────────────────────────────────────

  def _ensure_meeting(self, meeting_id: str) -> None:
    if meeting_id not in self._buffers:
      self._buffers[meeting_id] = []
      self._seen[meeting_id] = set()
      self._finalized_counts[meeting_id] = 0

  def _trim_buffer(self, meeting_id: str) -> None:
    """Evicts the oldest *partial* chunk when the buffer exceeds capacity.

    Finalized chunks are never evicted — they must be processed by the
    pipeline before the buffer can shrink below the finalized count.
    """
    buf = self._buffers[meeting_id]
    max_size = transcript_config.BUFFER_MAX_SIZE

    if len(buf) <= max_size:
      return

    # Find the first partial chunk (candidates for eviction)
    for i, chunk in enumerate(buf):
      if not chunk.is_final:
        evicted = buf.pop(i)
        # Remove its fingerprint so it can be re-delivered if needed
        fp = _chunk_fingerprint(evicted)
        self._seen[meeting_id].discard(fp)
        logger.debug(
            f"Buffer: Evicted oldest partial chunk for meeting={meeting_id} "
            f"(speaker={evicted.speaker_id}, start={evicted.start_time:.2f})"
        )
        return

    # All remaining chunks are final — log and do not trim
    logger.warning(
        f"Buffer: Over capacity ({len(buf)} > {max_size}) for meeting={meeting_id} "
        "but all chunks are finalized. Cannot evict safely."
    )
