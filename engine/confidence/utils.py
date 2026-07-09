"""
Utility Functions for the SCIE Confidence Engine (`engine/confidence/utils.py`).

Provides safe mathematical operations, boundary clamping, exponential staleness
decay, smooth recovery interpolation, and confidence trend classification.
"""
import math
import uuid
import time
from typing import List, Dict, Any
from engine.confidence.constants import ConfidenceTrend
from engine.confidence.config import confidence_config


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
  """Safely clamp a floating point number between `min_val` and `max_val`."""
  if math.isnan(value) or math.isinf(value):
    return min_val
  return max(min_val, min(max_val, float(value)))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
  """Safely divide numerator by denominator without ZeroDivisionError or NaN."""
  if denominator == 0.0 or math.isnan(denominator) or math.isinf(denominator):
    return default
  if math.isnan(numerator) or math.isinf(numerator):
    return default
  return float(numerator / denominator)


def calculate_exponential_decay(
    current_confidence: float,
    elapsed_stale_sec: float,
    decay_rate: float = confidence_config.CONFIDENCE_DECAY_RATE_PER_STEP
) -> float:
  """Calculate gradual confidence reduction over time when signals become stale or disappear.

  Does NOT drop instantly. Applies bounded half-life reduction proportional to elapsed time.
  """
  if elapsed_stale_sec <= confidence_config.EVIDENCE_STALE_TIMEOUT_SEC:
    return current_confidence

  # Calculate steps beyond threshold
  overdue_sec = elapsed_stale_sec - confidence_config.EVIDENCE_STALE_TIMEOUT_SEC
  steps = overdue_sec / 30.0  # Every 30 seconds of staleness counts as 1 decay step

  decay_factor = math.pow(1.0 - clamp(decay_rate, 0.01, 0.50), steps)
  decayed_val = current_confidence * decay_factor

  # Enforce max step drop limits
  max_drop = confidence_config.MAX_DECAY_PER_STEP * max(1.0, steps)
  bounded_val = max(current_confidence - max_drop, decayed_val)

  return clamp(bounded_val, 0.0, 1.0)


def calculate_smooth_recovery(
    previous_confidence: float,
    target_confidence: float,
    recovery_rate: float = confidence_config.CONFIDENCE_RECOVERY_RATE_PER_STEP
) -> float:
  """Smoothly interpolate upward when lost signals return (`UNAVAILABLE -> AVAILABLE`).

  Avoids sudden erratic spikes when evidence reappears after temporary dropout.
  """
  if target_confidence <= previous_confidence:
    return target_confidence

  delta = target_confidence - previous_confidence
  step_jump = min(delta * clamp(recovery_rate, 0.05, 1.0), confidence_config.MAX_RECOVERY_PER_STEP)
  recovered_val = previous_confidence + step_jump

  return clamp(recovered_val, 0.0, 1.0)


def classify_confidence_trend(history: List[Dict[str, Any]]) -> str:
  """Classify participant confidence trajectory (`UPWARD`, `DOWNWARD`, `STABLE`, `RECOVERING`)."""
  if not history or len(history) < 2:
    return ConfidenceTrend.STABLE.value

  # Inspect last 3 snapshots (or all if < 3)
  recent = history[-3:] if len(history) >= 3 else history
  scores = [float(item.get("confidence", item.get("current_confidence", 0.0))) for item in recent]

  delta = scores[-1] - scores[0]
  if abs(delta) < 0.03:
    return ConfidenceTrend.STABLE.value

  if delta > 0.0:
    # Check if this upward movement follows an earlier drop (RECOVERING vs UPWARD)
    if len(history) >= 4:
      earlier_score = float(history[-4].get("confidence", history[-4].get("current_confidence", scores[0])))
      if scores[0] < earlier_score - 0.05:
        return ConfidenceTrend.RECOVERING.value
    return ConfidenceTrend.UPWARD.value
  else:
    return ConfidenceTrend.DOWNWARD.value


def generate_event_id(prefix: str = "EV_") -> str:
  """Generate unique identifier for confidence state events."""
  return f"{prefix}{uuid.uuid4().hex[:12]}"


def current_timestamp_sec() -> float:
  """Get current high-precision UTC timestamp in seconds."""
  return time.time()
