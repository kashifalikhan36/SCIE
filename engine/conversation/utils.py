import time
import uuid
import hashlib
import json
import re
from typing import Any, Dict, List, Union
from engine.conversation.exceptions import JSONParseError
from engine.conversation.logger import logger


def now_ms() -> int:
  """Return the current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)


def generate_evidence_id() -> str:
  """Generate a unique 11-character identifier for ConversationEvidence (e.g. 'CE_4a9b2c1d')."""
  return f"CE_{uuid.uuid4().hex[:8]}"


def generate_chunk_id() -> str:
  """Generate a unique identifier for a conversation chunk."""
  return f"CHK_{uuid.uuid4().hex[:8]}"


def hash_transcript(data: Union[str, List[Any]]) -> str:
  """Generate a deterministic SHA-256 hex digest for a string or list of turns/chunks."""
  if isinstance(data, list):
    # Serialize list elements to canonical string
    raw = "\n".join(
        t.model_dump_json() if hasattr(t, "model_dump_json") else str(t)
        for t in data
    )
  else:
    raw = str(data)
  return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


def extract_json_from_response(raw_text: str) -> Dict[str, Any]:
  """Extract and parse structured JSON dictionary from raw model text output.

  Handles markdown code block wrapping (` ```json ... ``` `) and trailing junk.
  Raises JSONParseError if the input is not valid JSON dictionary.
  """
  if not raw_text or not raw_text.strip():
    raise JSONParseError("Received empty response string from model.")

  text = raw_text.strip()

  # Strip markdown code blocks if present
  if text.startswith("```"):
    # Strip opening fence (e.g., ```json or ```)
    first_newline = text.find("\n")
    if first_newline != -1:
      text = text[first_newline + 1 :]
    else:
      text = text[3:]
    # Strip closing fence
    if text.endswith("```"):
      text = text[:-3].strip()

  try:
    data = json.loads(text)
    if isinstance(data, dict):
      return data
    raise JSONParseError(f"Expected JSON dictionary object, got {type(data).__name__}")
  except json.JSONDecodeError as exc:
    # Attempt regex extraction of first {...} block as a fallback
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
      try:
        data = json.loads(match.group(1))
        if isinstance(data, dict):
          return data
      except Exception:
        pass
    logger.error(f"Failed to parse JSON from response: {text[:200]}...")
    raise JSONParseError(f"Malformed JSON response: {exc}") from exc
