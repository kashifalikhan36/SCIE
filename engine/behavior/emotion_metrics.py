from typing import Dict
from engine.behavior.models import EmotionMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class EmotionMetricsCalculator:
  """
  Aggregates facial emotion percentages observed by the Video Engine (if EmoNet integrated).

  Future-ready module. Does not perform raw image/emotion recognition directly.
  """

  def __init__(self):
    # participant_id -> {emotion_label: count}
    self._emotion_counts: Dict[str, Dict[str, int]] = {}

  def record_emotion(self, participant_id: str, emotion_label: str) -> None:
    """Record an observed emotion frame label for a participant."""
    if not participant_id or not emotion_label:
      return
    clean_label = emotion_label.strip().lower()
    if participant_id not in self._emotion_counts:
      self._emotion_counts[participant_id] = {}
    counts = self._emotion_counts[participant_id]
    counts[clean_label] = counts.get(clean_label, 0) + 1

  @measure_latency("emotion_metrics.calculate")
  def calculate(self, features: BehaviorFeatures) -> EmotionMetrics:
    """Calculate aggregate emotion percentages for the target participant."""
    try:
      pid = features.participant_id
      counts = self._emotion_counts.get(pid, {})
      total = sum(counts.values())

      if total == 0:
        # Check current latest feature
        if features.emotion == "happy":
          return EmotionMetrics(0.0, 100.0, 0.0, 0.0)
        elif features.emotion == "confused":
          return EmotionMetrics(0.0, 0.0, 100.0, 0.0)
        elif features.emotion == "surprised":
          return EmotionMetrics(0.0, 0.0, 0.0, 100.0)
        return EmotionMetrics(100.0, 0.0, 0.0, 0.0)

      neutral = safe_divide(float(counts.get("neutral", 0)), float(total)) * 100.0
      happy = safe_divide(float(counts.get("happy", 0)), float(total)) * 100.0
      confused = safe_divide(float(counts.get("confused", 0)), float(total)) * 100.0
      surprised = safe_divide(float(counts.get("surprised", 0)), float(total)) * 100.0

      return EmotionMetrics(
          neutral_percentage=round(neutral, 2),
          happy_percentage=round(happy, 2),
          confused_percentage=round(confused, 2),
          surprised_percentage=round(surprised, 2)
      )

    except Exception as e:
      logger.error(f"Error calculating emotion metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"EmotionMetrics calculation failed: {str(e)}") from e
