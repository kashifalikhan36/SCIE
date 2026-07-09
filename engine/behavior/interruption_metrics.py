from typing import List, Optional, Tuple
from engine.behavior.models import InterruptionMetrics, InterruptionEvent
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.config import behavior_config
from engine.behavior.utils import safe_divide, now_ms
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class InterruptionMetricsCalculator:
  """
  Detects and quantifies interruptions during the meeting.

  An interruption occurs when Speaker B begins speaking while Speaker A is currently speaking
  (overlap >= MIN_INTERRUPTION_DURATION_SEC).
  """

  def __init__(self):
    # History of detected interruption events across meetings
    self._history: List[InterruptionEvent] = []

  def detect_interruption(
      self,
      meeting_id: str,
      current_speaker_id: str,
      current_start: float,
      previous_speaker_id: str,
      previous_start: float,
      previous_end: float
  ) -> Optional[InterruptionEvent]:
    """Check if ``current_speaker_id`` interrupted ``previous_speaker_id`` based on timestamps."""
    if not current_speaker_id or not previous_speaker_id or current_speaker_id == previous_speaker_id:
      return None

    # Overlap occurs if current_start is before previous_end
    overlap = previous_end - current_start
    if overlap >= behavior_config.MIN_INTERRUPTION_DURATION_SEC:
      event = InterruptionEvent(
          meeting_id=meeting_id,
          interrupter_id=current_speaker_id,
          interrupted_id=previous_speaker_id,
          timestamp_ms=now_ms(),
          interrupter_turn_duration=overlap
      )
      self._history.append(event)
      logger.info(f"Interruption detected: {current_speaker_id} interrupted {previous_speaker_id} (overlap={overlap:.2f}s)")
      return event
    return None

  @measure_latency("interruption_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      meeting_duration_sec: float,
      interruption_events: Optional[List[InterruptionEvent]] = None
  ) -> InterruptionMetrics:
    """Calculate interruption metrics for the target participant."""
    try:
      pid = features.participant_id
      events = interruption_events if interruption_events is not None else self._history

      # Filter events where pid was the interrupter
      as_interrupter = [e for e in events if e.interrupter_id == pid or e.interrupter_id == features.speaker_id]
      # Filter events where pid was interrupted
      as_interrupted = [e for e in events if e.interrupted_id == pid or e.interrupted_id == features.speaker_id]

      count = max(features.interruptions, len(as_interrupter))

      # Frequency: interruptions per hour
      hrs = safe_divide(meeting_duration_sec, 3600.0)
      freq = safe_divide(float(count), hrs) if hrs > 0 else 0.0

      # Unique list of participants whom this participant interrupted
      interrupted_pids = sorted(list(set(e.interrupted_id for e in as_interrupter)))
      # Unique list of participants who interrupted this participant
      interrupting_pids = sorted(list(set(e.interrupter_id for e in as_interrupted)))

      return InterruptionMetrics(
          interruption_count=count,
          interruption_frequency=round(freq, 4),
          interrupted_participants=interrupted_pids,
          interrupting_participants=interrupting_pids
      )

    except Exception as e:
      logger.error(f"Error calculating interruption metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"InterruptionMetrics calculation failed: {str(e)}") from e

  def get_meeting_history(self, meeting_id: str) -> List[InterruptionEvent]:
    """Return all recorded interruption events for a specific meeting."""
    return [e for e in self._history if e.meeting_id == meeting_id]
