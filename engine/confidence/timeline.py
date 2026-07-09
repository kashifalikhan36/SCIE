"""
Confidence Timeline Manager (`engine/confidence/timeline.py`).

Maintains immutable chronological progression of participant confidence across time:
- Never overwrites previous checkpoints.
- Appends snapshots periodically based on `TIMELINE_RESOLUTION_SEC` (default 30s) or upon significant state transitions.
- Supports future graph visualization rendering.
- Classifies rolling trajectory trends (`UPWARD`, `DOWNWARD`, `STABLE`, `RECOVERING`).
"""
from typing import List, Dict, Any, Tuple
from engine.confidence.models import TimelineSnapshot
from engine.confidence.config import confidence_config
from engine.confidence.utils import classify_confidence_trend, clamp


class ConfidenceTimelineManager:
  """Manages rolling immutable history checkpoints for a participant."""

  def append_or_update_timeline(
      self,
      existing_history: List[Dict[str, Any]],
      current_timestamp: float,
      current_confidence: float,
      active_breakdown: Dict[str, float],
      reasons: List[str]
  ) -> Tuple[List[Dict[str, Any]], str, bool]:
    """Append a new historical snapshot if resolution elapsed or major delta occurred.

    Returns:
        tuple: (updated_history_list, classified_trend, was_snapshot_appended)
    """
    history_out = list(existing_history)
    trend = classify_confidence_trend(history_out)

    should_append = False
    if not history_out:
      should_append = True
    else:
      last_item = history_out[-1]
      last_ts = float(last_item.get("timestamp", 0.0))
      last_val = float(last_item.get("confidence", last_item.get("current_confidence", 0.0)))

      # Check if minimum time resolution elapsed (`>= 30s`) or if a major delta (`>= 0.15`) occurred
      if (current_timestamp - last_ts) >= confidence_config.TIMELINE_RESOLUTION_SEC:
        should_append = True
      elif abs(current_confidence - last_val) >= 0.15:
        should_append = True

    if should_append:
      snapshot = TimelineSnapshot(
          timestamp=current_timestamp,
          confidence=clamp(current_confidence, 0.0, 1.0),
          active_sources_count=len(active_breakdown),
          active_breakdown=dict(active_breakdown),
          trend=trend,
          reasons=list(reasons)
      )
      history_out.append(snapshot.as_dict())

      # Enforce rolling history memory limit
      if len(history_out) > confidence_config.MAX_TIMELINE_HISTORY_ITEMS:
        history_out = history_out[-confidence_config.MAX_TIMELINE_HISTORY_ITEMS:]

      # Re-classify trend after new item appended
      trend = classify_confidence_trend(history_out)

    return history_out, trend, should_append
