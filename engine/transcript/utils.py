import re
import uuid
import time
from typing import List


# ──────────────────────────────────────────────────────────────────────────────
# Text utilities
# ──────────────────────────────────────────────────────────────────────────────

def count_words(text: str) -> int:
  """Returns the number of words in *text*, ignoring extra whitespace.

  Uses word-boundary regex so punctuation attached to words does not
  inflate the count.
  """
  if not text:
    return 0
  return len(re.findall(r'\b\w+\b', text))


def normalize_text(text: str) -> str:
  """Collapses multiple spaces, strips leading/trailing whitespace."""
  if not text:
    return ""
  return re.sub(r'\s+', ' ', text).strip()


def merge_partial_texts(prev: str, new: str) -> str:
  """Returns the semantically fuller of two partial transcript strings.

  Whisper streaming sends progressively longer versions of the same
  utterance.  The correct update strategy is to replace with the new
  text whenever it is longer or contains the previous text as a prefix.

  Examples::

      merge_partial_texts("I have worked", "I have worked at")
      # → "I have worked at"

      merge_partial_texts("I have worked at Microsoft", "I have worked")
      # → "I have worked at Microsoft"  (new is shorter — keep prev)
  """
  if not prev:
    return new
  if not new:
    return prev
  prev_n = normalize_text(prev)
  new_n  = normalize_text(new)
  # If new text subsumes prev (prefix growth), take new.
  if new_n.startswith(prev_n) or len(new_n) >= len(prev_n):
    return new_n
  return prev_n


def extract_search_keywords(text: str, min_length: int = 4) -> List[str]:
  """Extracts significant, de-duplicated lowercase keywords from *text*.

  Words shorter than *min_length* characters are excluded to filter out
  stop-words (e.g. "is", "the", "and").  Results are deduplicated while
  preserving first-occurrence order.

  Designed to populate ``TranscriptEvidence.transcript_search_keywords``
  for future keyword / semantic search without additional schema changes.
  """
  if not text:
    return []
  words = re.findall(r'\b[a-zA-Z]\w+\b', text.lower())
  seen: set = set()
  keywords: List[str] = []
  for w in words:
    if len(w) >= min_length and w not in seen:
      seen.add(w)
      keywords.append(w)
  return keywords


# ──────────────────────────────────────────────────────────────────────────────
# Metrics utilities
# ──────────────────────────────────────────────────────────────────────────────

def compute_avg_wpm(word_count: int, duration_sec: float) -> float:
  """Computes words-per-minute from a word count and duration in seconds.

  Returns 0.0 for zero or negative durations to avoid division by zero.
  """
  if duration_sec <= 0.0 or word_count <= 0:
    return 0.0
  return round((word_count / duration_sec) * 60.0, 2)


# ──────────────────────────────────────────────────────────────────────────────
# ID / formatting utilities
# ──────────────────────────────────────────────────────────────────────────────

def generate_turn_id() -> str:
  """Generates a short, unique conversation turn identifier.

  Format: ``turn_<8-hex-chars>``  (e.g. ``turn_3f9a1b2c``)
  """
  return f"turn_{uuid.uuid4().hex[:8]}"


def format_timestamp_hms(seconds: float) -> str:
  """Formats a floating-point second offset as ``HH:MM:SS``.

  Useful for building human-readable timeline displays.

  Examples::

      format_timestamp_hms(0.0)    → "00:00:00"
      format_timestamp_hms(83.5)   → "00:01:23"
      format_timestamp_hms(3661.0) → "01:01:01"
  """
  total_seconds = max(0, int(seconds))
  hours, remainder = divmod(total_seconds, 3600)
  minutes, secs    = divmod(remainder, 60)
  return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def now_ms() -> int:
  """Returns the current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)
