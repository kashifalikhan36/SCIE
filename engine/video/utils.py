import cv2
import tempfile
import os
import logging
from typing import List, Tuple, Generator
import numpy as np

logger = logging.getLogger("SCIE.video_engine.utils")

def calculate_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
  """Calculates cosine similarity between two float vectors."""
  if not vec_a or not vec_b or len(vec_a) != len(vec_b):
    return 0.0
  
  a = np.array(vec_a)
  b = np.array(vec_b)
  
  norm_a = np.linalg.norm(a)
  norm_b = np.linalg.norm(b)
  
  if norm_a == 0.0 or norm_b == 0.0:
    return 0.0
    
  return float(np.dot(a, b) / (norm_a * norm_b))

def extract_frames_from_video_file(
    file_path: str, 
    target_fps: float,
    start_timestamp_ms: int = 0
) -> Generator[Tuple[int, int, np.ndarray], None, None]:
  """Decodes a video file using OpenCV and yields (frame_id, timestamp_ms, frame_image).
  
  Only yields frames sampled to match the configured target_fps.
  """
  cap = cv2.VideoCapture(file_path)
  if not cap.isOpened():
    logger.error(f"Failed to open video file for decoding: {file_path}")
    return

  try:
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
      fps = 30.0 # Default fallback FPS
      
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.debug(f"Video file opened: FPS={fps}, total frames={frame_count}")

    # Calculate frame step based on target sampling FPS
    frame_step = max(1, int(round(fps / target_fps)))
    
    frame_idx = 0
    sampled_count = 0
    
    while True:
      ret, frame = cap.read()
      if not ret:
        break
        
      if frame_idx % frame_step == 0:
        # Calculate timestamp of this frame relative to video start
        relative_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
        if relative_ms == 0 and frame_idx > 0:
          # Fallback timestamp estimation if POS_MSEC is unsupported/inaccurate
          relative_ms = int((frame_idx / fps) * 1000)
          
        absolute_timestamp = start_timestamp_ms + relative_ms
        yield frame_idx, absolute_timestamp, frame
        sampled_count += 1
        
      frame_idx += 1
      
    logger.info(f"Finished decoding video file. Total frames: {frame_idx}, sampled: {sampled_count}")
  finally:
    cap.release()
