import hashlib
import math
import re
import time
import uuid
from typing import List, Optional


def now_ms() -> int:
  """Returns current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)


def generate_evidence_id() -> str:
  """Generates a unique identity evidence ID with ``IE_`` prefix.

  Format: ``IE_<8-hex-chars>``  e.g. ``IE_3f9a1b2c``
  """
  return f"IE_{uuid.uuid4().hex[:8]}"


def hash_text(text: str) -> str:
  """Returns a stable SHA-256 hex digest of the input text.

  Used as the embedding cache key so identical strings always hit the
  same cache slot regardless of caller context.
  """
  return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
  """Computes cosine similarity between two float embedding vectors.

  Returns:
      float: A value in [-1.0, 1.0].  Returns 0.0 for empty/mismatched vectors
             or when either vector is the zero vector.
  """
  if not vec1 or not vec2 or len(vec1) != len(vec2):
    return 0.0
  dot = sum(a * b for a, b in zip(vec1, vec2))
  norm1 = math.sqrt(sum(a * a for a in vec1))
  norm2 = math.sqrt(sum(b * b for b in vec2))
  if norm1 <= 0.0 or norm2 <= 0.0:
    return 0.0
  return max(-1.0, min(1.0, dot / (norm1 * norm2)))


def embedding_distance(vec1: List[float], vec2: List[float]) -> float:
  """Returns L2 Euclidean distance between two embedding vectors.

  Useful as a secondary distance metric alongside cosine similarity.
  """
  if not vec1 or not vec2 or len(vec1) != len(vec2):
    return float("inf")
  return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))


def format_timestamp_ms(ms: int) -> str:
  """Formats epoch milliseconds into human readable ``HH:MM:SS`` format."""
  seconds = max(0, ms // 1000)
  hours, remainder = divmod(seconds, 3600)
  minutes, secs = divmod(remainder, 60)
  return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def safe_lower(text: Optional[str]) -> str:
  """Returns a lowercased stripped string or empty string if text is None."""
  if not text:
    return ""
  return text.strip().lower()


def truncate(text: str, max_len: int = 120) -> str:
  """Truncates a string to max_len characters with ellipsis."""
  if len(text) <= max_len:
    return text
  return text[:max_len - 3] + "..."
