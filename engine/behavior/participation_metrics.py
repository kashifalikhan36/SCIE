from engine.behavior.models import ParticipationMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide, clamp, now_ms
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class ParticipationMetricsCalculator:
  """
  Calculates presence, active time, idle time, and participation ratios for a participant.
  """

  @measure_latency("participation_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      meeting_duration_sec: float
  ) -> ParticipationMetrics:
    """Compute participation metrics based on presence and activity features."""
    try:
      # Total presence duration
      if features.join_time:
        end_ts = features.leave_time or features.last_activity or now_ms()
        presence_duration = max(0.0, float(end_ts - features.join_time) / 1000.0)
      else:
        presence_duration = max(features.speech_time + features.silent_time, 0.0)

      # If meeting_duration_sec is smaller than observed presence (due to slight desync), cap/adjust
      total_mtg = max(meeting_duration_sec, presence_duration)

      active_time = max(0.0, float(features.speech_time))
      idle_time = max(0.0, presence_duration - active_time)
      if idle_time == 0.0 and features.silent_time > 0:
        idle_time = features.silent_time

      # Participation percentage: active_time / total_mtg
      pct = safe_divide(active_time, total_mtg)
      pct = clamp(pct, 0.0, 1.0)

      # Active conversation ratio: active_time / presence_duration
      active_ratio = safe_divide(active_time, presence_duration) if presence_duration > 0 else 0.0
      active_ratio = clamp(active_ratio, 0.0, 1.0)

      # Speaking-to-listening ratio: active_time / idle_time
      spk_to_list = safe_divide(active_time, idle_time) if idle_time > 0 else (1.0 if active_time > 0 else 0.0)

      return ParticipationMetrics(
          participation_percentage=round(pct, 4),
          active_time=round(active_time, 4),
          idle_time=round(idle_time, 4),
          total_meeting_presence=round(presence_duration, 4),
          active_conversation_ratio=round(active_ratio, 4),
          speaking_to_listening_ratio=round(spk_to_list, 4)
      )

    except Exception as e:
      logger.error(f"Error calculating participation metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"ParticipationMetrics calculation failed: {str(e)}") from e
