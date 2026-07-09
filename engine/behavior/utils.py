import time
import uuid
import re
from typing import Optional


def now_ms() -> int:
  """Return the current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)


def generate_evidence_id() -> str:
  """Generate a unique 11-character identifier for BehaviorEvidence (e.g. 'BE_4a9b2c1d')."""
  return f"BE_{uuid.uuid4().hex[:8]}"


def generate_timeline_id() -> str:
  """Generate a unique identifier for a timeline entry."""
  return f"BTL_{uuid.uuid4().hex[:8]}"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
  """Safely divide two numbers, returning ``default`` if denominator is zero."""
  if not denominator or abs(denominator) < 1e-9:
    return default
  return float(numerator) / float(denominator)


def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
  """Clamp a numeric value strictly within [min_val, max_val]."""
  if val < min_val:
    return min_val
  if val > max_val:
    return max_val
  return val


def format_timestamp_ms(ts_ms: int) -> str:
  """Format epoch milliseconds into HH:MM:SS string."""
  if ts_ms <= 0:
    return "00:00:00"
  seconds = int(ts_ms / 1000)
  hrs = seconds // 3600
  mins = (seconds % 3600) // 60
  secs = seconds % 60
  return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def format_duration_sec(duration_sec: float) -> str:
  """Format duration in seconds into HH:MM:SS string."""
  if duration_sec <= 0:
    return "00:00:00"
  seconds = int(duration_sec)
  hrs = seconds // 3600
  mins = (seconds % 3600) // 60
  secs = seconds % 60
  return f"{hrs:02d}:{mins:02d}:{secs:02d}"


_QUESTION_STARTERS = (
    "what", "when", "where", "why", "who", "how",
    "can", "could", "would", "should", "do", "does", "did",
    "is", "are", "was", "were", "have", "has", "had", "will", "may", "might"
)


def is_question(text: Optional[str]) -> bool:
  """Check if text appears to be a question based on punctuation and starting words."""
  if not text:
    return False
  clean = text.strip().lower()
  if clean.endswith("?"):
    return True
  words = re.findall(r"\b\w+\b", clean)
  if words and words[0] in _QUESTION_STARTERS and len(words) > 2:
    return True
  return False


def truncate(s: str, max_len: int = 120) -> str:
  """Truncate a string to at most ``max_len`` characters."""
  if not s or len(s) <= max_len:
    return s
  return s[: max_len - 3] + "..."
