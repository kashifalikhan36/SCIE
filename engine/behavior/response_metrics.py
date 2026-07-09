import math
from typing import List, Optional
from engine.behavior.models import ResponseMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class ResponseMetricsCalculator:
  """
  Calculates response delays, consistency, answer lengths, and reply durations
  using transcript and utterance timestamps.
  """

  @measure_latency("response_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      response_delays: Optional[List[float]] = None,
      reply_durations: Optional[List[float]] = None,
      reply_words: Optional[List[int]] = None
  ) -> ResponseMetrics:
    """Compute response dynamics given observed delay intervals and reply counts."""
    try:
      # Compute response delays
      if response_delays and len(response_delays) > 0:
        avg_delay = safe_divide(sum(response_delays), float(len(response_delays)))
        fastest = min(response_delays)
        slowest = max(response_delays)

        # Consistency: 1 / (1 + variance) where variance = avg((x - mean)^2)
        if len(response_delays) > 1:
          variance = sum((x - avg_delay) ** 2 for x in response_delays) / float(len(response_delays))
          consistency = 1.0 / (1.0 + math.sqrt(variance))
        else:
          consistency = 1.0
      else:
        # Default or estimate from features
        avg_delay = features.average_response_time or 0.0
        fastest = avg_delay
        slowest = avg_delay
        consistency = 1.0 if avg_delay > 0 else 0.0

      # Compute answer length and reply duration
      ans_count = max(0, int(features.response_count))
      if reply_durations and len(reply_durations) > 0:
        avg_reply_dur = safe_divide(sum(reply_durations), float(len(reply_durations)))
      else:
        avg_reply_dur = safe_divide(features.speech_time, float(features.turn_count)) if features.turn_count > 0 else 0.0

      if reply_words and len(reply_words) > 0:
        avg_ans_words = safe_divide(float(sum(reply_words)), float(len(reply_words)))
      else:
        avg_ans_words = safe_divide(float(features.word_count), float(features.turn_count)) if features.turn_count > 0 else 0.0

      return ResponseMetrics(
          average_response_delay=round(avg_delay, 4),
          fastest_response=round(fastest, 4),
          slowest_response=round(slowest, 4),
          response_consistency=round(consistency, 4),
          average_answer_length_words=round(avg_ans_words, 2),
          average_reply_duration=round(avg_reply_dur, 4)
      )

    except Exception as e:
      logger.error(f"Error calculating response metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"ResponseMetrics calculation failed: {str(e)}") from e
