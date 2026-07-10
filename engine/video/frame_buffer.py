import logging
from typing import List, Dict, Optional
from engine.video.schemas import VideoChunk
from engine.video.config import video_config

logger = logging.getLogger("SCIE.video_engine.frame_buffer")

class VideoFrameBuffer:
  """Buffers, reorders, and ensures sequential alignment of incoming video chunks."""

  def __init__(self, window_size_chunks: int = 1):
    self.window_size_chunks = window_size_chunks
    self.pending_chunks: Dict[int, VideoChunk] = {}
    self.expected_index = 1
    # Allow gaps of up to 4 chunks (1 second of video if chunks are 250ms)
    self.max_gap_chunks = 4

  def add_chunk(self, chunk: VideoChunk):
    """Adds a new video chunk to the buffer."""
    idx = chunk.chunk_index

    # Bootstrap: if the buffer is empty and the first chunk's index is far ahead of
    # expected_index (cross-session gap), snap expected_index to match it so we
    # don't log hundreds of false gap warnings.
    if not self.pending_chunks and (idx - self.expected_index) > self.max_gap_chunks:
      logger.info(f"Bootstrapping video expected_index to {idx} from first received chunk")
      self.expected_index = idx

    if idx < self.expected_index:
      logger.warning(f"Discarding late video chunk {idx} (expected >= {self.expected_index})")
      return

    self.pending_chunks[idx] = chunk
    logger.debug(f"Buffered video chunk {idx} (expected {self.expected_index})")

    # Detect and handle gaps (missing chunks)
    self._handle_gaps()

  def _handle_gaps(self):
    """Detects missing chunks and force-advances the expected index to recover."""
    if not self.pending_chunks:
      return

    max_buffered_idx = max(self.pending_chunks.keys())
    
    if max_buffered_idx - self.expected_index >= self.max_gap_chunks:
      # Find first missing index starting from expected_index
      missing_idx = self.expected_index
      while missing_idx in self.pending_chunks:
        missing_idx += 1
        
      # Find next available index after that missing index
      buffered_after_gap = sorted(k for k in self.pending_chunks.keys() if k > missing_idx)
      if buffered_after_gap:
        next_available_idx = buffered_after_gap[0]
        
        # Clean up orphaned chunks prior to the new index
        for i in list(self.pending_chunks.keys()):
          if i < next_available_idx:
            logger.warning(f"Discarding orphaned video chunk {i} due to missing downstream chunks")
            del self.pending_chunks[i]
            
        logger.warning(f"Video Gap detected! Advancing expected index from {self.expected_index} to {next_available_idx}")
        self.expected_index = next_available_idx

  def get_next_window(self) -> Optional[List[VideoChunk]]:
    """Returns a list of sequential chunks forming the next window, or None if not ready."""
    window_chunks: List[VideoChunk] = []
    
    for i in range(self.window_size_chunks):
      target_idx = self.expected_index + i
      if target_idx in self.pending_chunks:
        window_chunks.append(self.pending_chunks[target_idx])
      else:
        # Gap present, window is not ready
        return None

    # Dequeue from pending set
    for chunk in window_chunks:
      del self.pending_chunks[chunk.chunk_index]

    # Advance expected index
    self.expected_index += self.window_size_chunks
    return window_chunks
