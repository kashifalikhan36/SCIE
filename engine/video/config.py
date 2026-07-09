import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class VideoEngineSettings(BaseSettings):
  """Video Engine configuration settings loaded from environment or defaults."""
  
  # Frame sampling rate (FPS) to reduce compute
  SAMPLING_FPS: float = 2.0
  
  # MediaPipe face detection confidence threshold
  MIN_FACE_CONFIDENCE: float = 0.5
  
  # Minimum size of face boundary box (width or height in pixels)
  MIN_FACE_SIZE: int = 30
  
  # Tracking parameter: maximum frames a track can be missing before being deleted
  TRACK_MAX_AGE_FRAMES: int = 30
  
  # InsightFace recognition parameter: refresh embedding interval (in frames) for active tracks
  RECOGNITION_REFRESH_INTERVAL: int = 10
  
  # Embedding matcher parameter: similarity threshold for matching faces
  COSINE_SIMILARITY_THRESHOLD: float = 0.60
  
  # Async Queue parameters
  WORKER_QUEUE_MAXSIZE: int = 100
  WORKER_COUNT: int = 2
  
  # Reordering stream parameters
  BUFFER_MAX_GAP_MS: int = 1500

  model_config = SettingsConfigDict(env_prefix="VIDEO_", case_sensitive=True)

video_config = VideoEngineSettings()
