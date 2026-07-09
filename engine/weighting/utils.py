"""
Utility helpers for the SCIE Dynamic Weighting Engine.

Provides safe arithmetic, timestamp formatting, bounding calculations, and ID generation.
(`engine/weighting/utils.py`)
"""
import time
import uuid
import math
from datetime import datetime, timezone
from typing import Union


def now_ms() -> int:
  """Return current UTC epoch timestamp in milliseconds."""
  return int(time.time() * 1000)


def format_timestamp_ms(ts_ms: int) -> str:
  """Format millisecond epoch timestamp into ISO 8601 string."""
  dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
  return dt.isoformat()


def clamp(value: float, min_val: float, max_val: float) -> float:
  """Safely clamp a numeric value to the bounds [min_val, max_val], handling NaN/Inf."""
  if value is None or math.isnan(value):
    return min_val
  if math.isinf(value):
    return max_val if value > 0 else min_val
  return max(min_val, min(max_val, float(value)))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
  """Perform division safely, returning default if denominator is zero or near-zero."""
  if denominator is None or abs(denominator) < 1e-12:
    return default
  try:
    res = numerator / denominator
    if math.isnan(res) or math.isinf(res):
      return default
    return res
  except (ZeroDivisionError, OverflowError):
    return default


def calculate_time_decay(age_sec: float, half_life_sec: float = 60.0) -> float:
  """Calculate exponential decay multiplier based on half-life formula: 0.5 ** (age / half_life)."""
  if age_sec <= 0.0:
    return 1.0
  if half_life_sec <= 0.0:
    return 0.0
  try:
    decay = 0.5 ** (age_sec / half_life_sec)
    return clamp(decay, 0.0, 1.0)
  except (OverflowError, ValueError):
    return 0.0


def generate_profile_id() -> str:
  """Generate unique identifier for a DynamicWeightProfile."""
  return f"DWP_{uuid.uuid4().hex[:12].upper()}"
