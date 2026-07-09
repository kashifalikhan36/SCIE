import math
import re
import time
import uuid
from typing import List, Optional


def generate_participant_id() -> str:
  """Generates a short, deterministic-prefix unique participant identifier.

  Format: ``P_<8-hex-chars>`` (e.g. ``P_3f9a1b2c``)
  """
  return f"P_{uuid.uuid4().hex[:8]}"


def now_ms() -> int:
  """Returns current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)


def format_timestamp(ms: int) -> str:
  """Formats epoch milliseconds into human readable ``HH:MM:SS`` format."""
  seconds = max(0, ms // 1000)
  hours, remainder = divmod(seconds, 3600)
  minutes, secs = divmod(remainder, 60)
  return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def clean_string(text: Optional[str]) -> str:
  """Normalizes string for robust matching: lowercase, strip punctuation/spaces."""
  if not text:
    return ""
  # Remove punctuation and excess whitespace
  cleaned = re.sub(r'[^\w\s@.]', ' ', str(text).lower())
  return re.sub(r'\s+', ' ', cleaned).strip()


def compute_time_overlap(
    start1: float, end1: float, start2: float, end2: float
) -> float:
  """Returns the overlapping duration (in seconds) between two time intervals.

  Returns 0.0 if the intervals do not overlap.
  """
  overlap_start = max(start1, start2)
  overlap_end = min(end1, end2)
  return max(0.0, overlap_end - overlap_start)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
  """Computes cosine similarity between two numerical embedding vectors.

  Returns 0.0 if vectors are empty, mismatched in length, or zero-magnitude.
  """
  if not vec1 or not vec2 or len(vec1) != len(vec2):
    return 0.0
  dot = sum(a * b for a, b in zip(vec1, vec2))
  norm1 = math.sqrt(sum(a * a for a in vec1))
  norm2 = math.sqrt(sum(b * b for b in vec2))
  if norm1 <= 0.0 or norm2 <= 0.0:
    return 0.0
  # Clamp between -1.0 and 1.0 to guard against floating-point jitter
  return max(-1.0, min(1.0, dot / (norm1 * norm2)))
