import os
import tempfile
import logging
from typing import Generator, Tuple, List
import numpy as np
from engine.video.schemas import VideoChunk
from engine.video.utils import extract_frames_from_video_file
from engine.video.config import video_config

logger = logging.getLogger("SCIE.video_engine.frame_sampler")

class VideoFrameSampler:
  """Decodes video stream chunks and samples frames at a configurable rate."""

  def __init__(self, target_fps: float = video_config.SAMPLING_FPS):
    self.target_fps = target_fps

  def sample_frames(self, chunk: VideoChunk) -> List[Tuple[int, int, np.ndarray]]:
    """Decodes and samples frames from a single video chunk.
    
    Returns a list of tuples: (frame_idx, timestamp_ms, frame_image).
    """
    sampled_frames: List[Tuple[int, int, np.ndarray]] = []
    
    # Resolve the video file path
    temp_file = None
    file_path = chunk.file_path

    try:
      # If no file path exists, write bytes to a temp file
      if not file_path or not os.path.exists(file_path):
        temp_file = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        temp_file.write(chunk.data)
        temp_file.close()
        file_path = temp_file.name

      # Use utility to extract frames
      # The base timestamp is chunk.timestamp
      for frame_id, ts, img in extract_frames_from_video_file(file_path, self.target_fps, chunk.timestamp):
        sampled_frames.append((frame_id, ts, img))
        
      logger.info(f"Sampled {len(sampled_frames)} frames from chunk {chunk.chunk_index}")
      return sampled_frames

    except Exception as e:
      logger.error(f"Error sampling frames from chunk {chunk.chunk_index}: {e}")
      return []
    finally:
      # Clean up temp file if one was created
      if temp_file is not None and os.path.exists(temp_file.name):
        try:
          os.unlink(temp_file.name)
        except Exception as cleanup_err:
          logger.warning(f"Failed to delete temp video file {temp_file.name}: {cleanup_err}")
