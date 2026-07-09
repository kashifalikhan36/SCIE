from typing import Dict
from engine.behavior.models import GazeMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide, clamp
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class GazeMetricsCalculator:
  """
  Aggregates gaze directions observed by the Video Engine (if L2CS-Net integrated).

  Future-ready module. Does not perform raw image/gaze estimation directly.
  """

  def __init__(self):
    # participant_id -> {gaze_label: count}
    self._gaze_counts: Dict[str, Dict[str, int]] = {}

  def record_gaze(self, participant_id: str, gaze_label: str) -> None:
    """Record an observed gaze direction label for a participant."""
    if not participant_id or not gaze_label:
      return
    clean_label = gaze_label.strip().lower()
    if participant_id not in self._gaze_counts:
      self._gaze_counts[participant_id] = {}
    counts = self._gaze_counts[participant_id]
    counts[clean_label] = counts.get(clean_label, 0) + 1

  @measure_latency("gaze_metrics.calculate")
  def calculate(self, features: BehaviorFeatures) -> GazeMetrics:
    """Calculate aggregate gaze and attention percentages for the target participant."""
    try:
      pid = features.participant_id
      counts = self._gaze_counts.get(pid, {})
      total = sum(counts.values())

      if total == 0:
        # Check current latest feature
        if features.gaze_direction == "looking_away":
          return GazeMetrics(0.0, 100.0, 0.0, 0.0)
        elif features.gaze_direction == "looking_down":
          return GazeMetrics(0.0, 0.0, 100.0, 0.0)
        return GazeMetrics(100.0, 0.0, 0.0, 1.0)

      at_screen = safe_divide(float(counts.get("looking_at_screen", 0)), float(total)) * 100.0
      away = safe_divide(float(counts.get("looking_away", 0)), float(total)) * 100.0
      down = safe_divide(float(counts.get("looking_down", 0)), float(total)) * 100.0

      # Attention ratio: looking_at_screen / total
      attn_ratio = safe_divide(float(counts.get("looking_at_screen", 0)), float(total))
      attn_ratio = clamp(attn_ratio, 0.0, 1.0)

      return GazeMetrics(
          looking_at_screen_percentage=round(at_screen, 2),
          looking_away_percentage=round(away, 2),
          looking_down_percentage=round(down, 2),
          attention_ratio=round(attn_ratio, 4)
      )

    except Exception as e:
      logger.error(f"Error calculating gaze metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"GazeMetrics calculation failed: {str(e)}") from e
