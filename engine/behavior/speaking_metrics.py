from typing import List
from engine.behavior.models import SpeakingMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide, clamp
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class SpeakingMetricsCalculator:
  """
  Calculates speaking duration, WPM, turns, and pause dynamics for a participant.
  """

  @measure_latency("speaking_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      meeting_duration_sec: float,
      turn_durations: Optional[List[float]] = None,
      pause_durations: Optional[List[float]] = None
  ) -> SpeakingMetrics:
    """Compute current speaking metrics given cumulative features and meeting duration."""
    try:
      total_speech = max(0.0, float(features.speech_time))
      turns = max(0, int(features.turn_count))
      words = max(0, int(features.word_count))

      avg_duration = safe_divide(total_speech, float(turns)) if turns > 0 else 0.0

      # Determine longest and shortest turn
      if turn_durations and len(turn_durations) > 0:
        longest = max(turn_durations)
        shortest = min(turn_durations)
      else:
        longest = max(features.longest_monologue, avg_duration)
        shortest = avg_duration if turns > 0 else 0.0

      speaking_pct = safe_divide(total_speech, meeting_duration_sec) if meeting_duration_sec > 0 else 0.0
      speaking_pct = clamp(speaking_pct, 0.0, 1.0)

      # WPM: words / (total_speech / 60.0)
      minutes_spoken = safe_divide(total_speech, 60.0)
      avg_wpm = safe_divide(float(words), minutes_spoken) if minutes_spoken > 0 else 0.0

      # Pause duration
      if pause_durations and len(pause_durations) > 0:
        avg_pause = safe_divide(sum(pause_durations), float(len(pause_durations)))
      else:
        # Estimate pause duration based on silent time divided by turns
        avg_pause = safe_divide(features.silent_time, float(turns)) if turns > 0 else 0.0

      metrics = SpeakingMetrics(
          total_speaking_duration=round(total_speech, 4),
          average_speaking_duration=round(avg_duration, 4),
          longest_speaking_turn=round(longest, 4),
          shortest_speaking_turn=round(shortest, 4),
          speaking_percentage=round(speaking_pct, 4),
          number_of_speaking_turns=turns,
          average_words_per_minute=round(avg_wpm, 2),
          average_pause_duration=round(avg_pause, 4)
      )
      return metrics

    except Exception as e:
      logger.error(f"Error calculating speaking metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"SpeakingMetrics calculation failed: {str(e)}") from e
