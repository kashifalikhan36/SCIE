import logging
from typing import Dict, List, Optional
from engine.audio.config import audio_config
from engine.audio.schemas import AudioChunk
from engine.audio.exceptions import AudioBufferError

logger = logging.getLogger("SCIE.audio_engine.buffer")

class AudioBuffer:
  """Intelligent streaming buffer that reorders chunks, combines them into windows, and recovers missing chunks."""

  def __init__(self, window_size_ms: int = audio_config.BUFFER_WINDOW_SIZE_MS):
    self.window_size_ms = window_size_ms
    # Default chunk duration; auto-calibrated from real chunk timestamps on first two chunks.
    self.chunk_duration_ms = 250
    self.chunks_per_window = max(1, window_size_ms // self.chunk_duration_ms)
    self._last_chunk_timestamp: int | None = None
    self._last_chunk_index: int | None = None
    self._calibrated = False

    # Store pending chunks by index: {index: AudioChunk}
    self.pending_chunks: Dict[int, AudioChunk] = {}
    self.expected_index = 1
    self.max_gap_chunks = max(4, self.chunks_per_window * 2)

  def add_chunk(self, chunk: AudioChunk):
    """Add a new audio chunk to the buffer."""
    idx = chunk.chunk_index

    # Auto-calibrate chunk_duration_ms from real chunk timestamps.
    # Only calibrate when two consecutive sequential chunk indices arrive in order.
    if not self._calibrated and chunk.timestamp:
      if (self._last_chunk_timestamp is not None and
          self._last_chunk_index is not None and
          idx == self._last_chunk_index + 1):
        delta_ms = abs(chunk.timestamp - self._last_chunk_timestamp)
        if 100 <= delta_ms <= 2000:  # sanity-check: between 100ms and 2s
          self.chunk_duration_ms = delta_ms
          self.chunks_per_window = max(1, self.window_size_ms // self.chunk_duration_ms)
          self.max_gap_chunks = max(4, self.chunks_per_window * 2)
          self._calibrated = True
          logger.info(f"Audio buffer calibrated: chunk_duration={delta_ms}ms, chunks_per_window={self.chunks_per_window}")
      self._last_chunk_timestamp = chunk.timestamp
      self._last_chunk_index = idx

    # Bootstrap: if the buffer is empty and the first chunk's index is far ahead of
    # expected_index (cross-session gap), snap expected_index to match it so we
    # don't log hundreds of false gap warnings.
    if not self.pending_chunks and (idx - self.expected_index) > self.max_gap_chunks:
      logger.info(f"Bootstrapping audio expected_index to {idx} from first received chunk")
      self.expected_index = idx

    if idx < self.expected_index:
      logger.warning(f"Discarding late chunk {idx} (expected >= {self.expected_index})")
      return

    self.pending_chunks[idx] = chunk
    logger.debug(f"Buffered chunk {idx} (expected {self.expected_index})")

    # Detect and handle gaps (missing chunks)
    self._handle_gaps()

  def _handle_gaps(self):
    """Detects missing chunks and force-advances the expected index to recover."""
    if not self.pending_chunks:
      return

    max_buffered_idx = max(self.pending_chunks.keys())
    
    # If the gap between the highest buffered chunk and expected index exceeds threshold,
    # we assume intermediate chunks are lost and force-advance expected_index
    if max_buffered_idx - self.expected_index >= self.max_gap_chunks:
      # Find the first missing index starting from expected_index
      missing_idx = self.expected_index
      while missing_idx in self.pending_chunks:
        missing_idx += 1
        
      # Find the next available index after that missing index
      buffered_after_gap = sorted(k for k in self.pending_chunks.keys() if k > missing_idx)
      if buffered_after_gap:
        next_available_idx = buffered_after_gap[0]
        
        # Discard any buffered chunks that were before the missing index
        # (since they can never form a complete window now that the sequence is broken)
        for i in list(self.pending_chunks.keys()):
          if i < next_available_idx:
            logger.warning(f"Discarding orphaned chunk {i} due to missing downstream chunks")
            del self.pending_chunks[i]
            
        logger.warning(f"Gap detected! Advancing expected index from {self.expected_index} to {next_available_idx}")
        self.expected_index = next_available_idx

  def get_next_window(self) -> Optional[List[AudioChunk]]:
    """Returns a list of sequential chunks forming the next processing window, or None if not ready."""
    window_chunks: List[AudioChunk] = []
    
    # Check if we have the next full sequence of chunks
    for i in range(self.chunks_per_window):
      target_idx = self.expected_index + i
      if target_idx in self.pending_chunks:
        window_chunks.append(self.pending_chunks[target_idx])
      else:
        # Not ready yet: sequence is broken or not enough chunks are buffered
        return None

    # Consume and return the window
    for chunk in window_chunks:
      del self.pending_chunks[chunk.chunk_index]
    
    self.expected_index += self.chunks_per_window
    logger.info(f"Assembled window with {len(window_chunks)} chunks (next expected: {self.expected_index})")
    return window_chunks

  def clear(self):
    """Resets the buffer state."""
    self.pending_chunks.clear()
    self.expected_index = 1
    self._last_chunk_timestamp = None
    self._last_chunk_index = None
    self._calibrated = False
    self.chunk_duration_ms = 250
    self.chunks_per_window = max(1, self.window_size_ms // self.chunk_duration_ms)
    self.max_gap_chunks = max(4, self.chunks_per_window * 2)
