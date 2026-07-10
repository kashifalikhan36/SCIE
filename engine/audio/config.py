import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class AudioEngineSettings(BaseSettings):
  # API key for Azure Speech
  AZURE_OPENAI_API_KEY: str = ""
  AZURE_OPENAI_ENDPOINT: str = ""
  
  # Hugging Face Hub token (Required for Pyannote models)
  HF_TOKEN: str = ""

  # Voice Activity Detection (VAD) thresholds
  VAD_SPEECH_THRESHOLD: float = 0.5
  VAD_MIN_SPEECH_DURATION: float = 0.25 # in seconds

  # Speaker Recognition / Identification thresholds
  SPEAKER_SIMILARITY_THRESHOLD: float = 0.75 # Cosine similarity threshold
  
  # Audio Stream Buffer Configuration
  # Increased to 3000ms to give Azure Speech enough context for recognize_once()
  BUFFER_WINDOW_SIZE_MS: int = 3000 
  BUFFER_MAX_GAP_MS: int = 500 # max allowed chunk gap in ms

  # Worker Thread / Pipeline Queue Configuration
  WORKER_QUEUE_MAXSIZE: int = 100
  WORKER_COUNT: int = 2
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 1.0

  model_config = SettingsConfigDict(
      env_file=".env",
      extra="ignore"
  )

audio_config = AudioEngineSettings()
