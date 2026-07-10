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
    # 500ms per chunk (Chrome Extension records 500ms audio chunks)
    self.chunk_duration_ms = 500
    self.chunks_per_window = max(1, window_size_ms // self.chunk_duration_ms)
    
    # Store pending chunks by index: {index: AudioChunk}
    self.pending_chunks: Dict[int, AudioChunk] = {}
    self.expected_index = 1
    self.max_gap_chunks = max(4, self.chunks_per_window * 2)

  def add_chunk(self, chunk: AudioChunk):
    """Add a new audio chunk to the buffer."""
    idx = chunk.chunk_index

    # Bootstrap: on the very first chunk, align expected_index to its actual index.
    # This handles sessions where the MeetingStore file counter continues from a
    # previous run (e.g. chunk 191 arriving when buffer expects 1).
    if not self.pending_chunks and idx > self.expected_index:
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
