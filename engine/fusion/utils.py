"""
Utility functions for the Evidence Fusion Engine (`engine/fusion/`).

Provides time utilities, ID generators, safe mathematical operations, and freshness decay calculations.
"""
import time
import uuid
import math


def now_ms() -> int:
  """Return current UTC epoch time in milliseconds."""
  return int(time.time() * 1000)


def generate_fusion_event_id() -> str:
  """Generate a unique identifier for a fusion event or snapshot (e.g., 'FE_4a9b2c1d')."""
  return f"FE_{uuid.uuid4().hex[:8]}"


def generate_explanation_id() -> str:
  """Generate a unique identifier for a structured explanation object (e.g., 'EX_4a9b2c1d')."""
  return f"EX_{uuid.uuid4().hex[:8]}"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
  """Safely divide two numbers, returning `default` if denominator is zero or near zero."""
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


def calculate_time_decay(age_sec: float, half_life_sec: float = 60.0) -> float:
  """Calculate exponential freshness multiplier (0.0 to 1.0) given signal age in seconds and decay half life.

  If age_sec <= 0, returns 1.0.
  If half_life_sec <= 0, returns 0.0 when age_sec > 0.
  """
  if age_sec <= 0.0:
    return 1.0
  if half_life_sec <= 0.0:
    return 0.0
  decay = math.pow(0.5, age_sec / float(half_life_sec))
  return clamp(decay, 0.0, 1.0)
