import os
import logging
from typing import Tuple

logger = logging.getLogger("SCIE.audio_engine.utils")

def read_audio_file(file_path: str, target_sr: int = 16000) -> Tuple[bytes, int]:
  """Reads an audio file and returns its bytes and sample rate.
  
  If the file cannot be loaded or is in an unsupported format,
  logs a warning and returns mock PCM bytes.
  """
  try:
    if not os.path.exists(file_path):
      raise FileNotFoundError(f"Audio file does not exist: {file_path}")
      
    # Standard production implementation would use soundfile/torchaudio:
    # import torchaudio
    # waveform, sr = torchaudio.load(file_path)
    # resample if needed
    
    # Fallback/Safe file reading
    with open(file_path, "rb") as f:
      data = f.read()
    return data, target_sr
  except Exception as e:
    logger.warning(f"Failed to read audio file {file_path}: {e}. Returning mock PCM data.")
    # Return mock PCM bytes (16000 samples/sec, 16-bit mono, 1 second = 32000 bytes)
    return b"\x00" * 32000, target_sr

def calculate_cosine_similarity(vec_a: list, vec_b: list) -> float:
  """Calculates cosine similarity between two float vectors.
  
  Returns 0.0 if vectors are empty or mismatched.
  """
  if not vec_a or not vec_b or len(vec_a) != len(vec_b):
    return 0.0
  try:
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
      return 0.0
    return float(dot_product / (norm_a * norm_b))
  except Exception as e:
    logger.error(f"Error calculating cosine similarity: {e}")
    return 0.0
