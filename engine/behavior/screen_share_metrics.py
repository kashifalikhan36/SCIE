from typing import Optional, Dict
from engine.behavior.models import ScreenShareMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import now_ms
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class ScreenShareMetricsCalculator:
  """
  Tracks screen sharing durations, session counts, and start/end timestamps.
  """

  def __init__(self):
    # participant_id -> state tracking
    self._session_start: Dict[str, float] = {}
    self._total_duration: Dict[str, float] = {}
    self._sessions_count: Dict[str, int] = {}
    self._first_time: Dict[str, float] = {}
    self._latest_time: Dict[str, float] = {}

  def record_session_start(self, participant_id: str, start_time_sec: Optional[float] = None) -> None:
    """Record the start of a screen share session."""
    ts = start_time_sec if start_time_sec is not None else float(now_ms()) / 1000.0
    self._session_start[participant_id] = ts
    self._latest_time[participant_id] = ts
    if participant_id not in self._first_time:
      self._first_time[participant_id] = ts
    self._sessions_count[participant_id] = self._sessions_count.get(participant_id, 0) + 1
    logger.info(f"Screen share started for {participant_id} at {ts:.2f}s")

  def record_session_end(self, participant_id: str, end_time_sec: Optional[float] = None) -> None:
    """Record the end of a screen share session and accumulate duration."""
    ts = end_time_sec if end_time_sec is not None else float(now_ms()) / 1000.0
    self._latest_time[participant_id] = ts
    if participant_id in self._session_start:
      start = self._session_start.pop(participant_id)
      duration = max(0.0, ts - start)
      self._total_duration[participant_id] = self._total_duration.get(participant_id, 0.0) + duration
      logger.info(f"Screen share ended for {participant_id} (duration: {duration:.2f}s)")

  @measure_latency("screen_share_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      current_meeting_time_sec: Optional[float] = None
  ) -> ScreenShareMetrics:
    """Calculate current screen share metrics for the target participant."""
    try:
      pid = features.participant_id
      total_dur = self._total_duration.get(pid, 0.0)

      # If currently sharing, add ongoing duration
      if pid in self._session_start or features.screen_share:
        start_ts = self._session_start.get(pid, float(features.join_time or now_ms()) / 1000.0)
        curr_ts = current_meeting_time_sec if current_meeting_time_sec is not None else float(now_ms()) / 1000.0
        ongoing = max(0.0, curr_ts - start_ts)
        # Avoid double-counting or insane timestamps
        if ongoing < 86400.0:
          total_dur += ongoing

      sessions = self._sessions_count.get(pid, 1 if features.screen_share else 0)

      return ScreenShareMetrics(
          total_screen_share_duration=round(total_dur, 4),
          number_of_screen_share_sessions=sessions,
          first_screen_share_time=self._first_time.get(pid),
          latest_screen_share_time=self._latest_time.get(pid)
      )

    except Exception as e:
      logger.error(f"Error calculating screen share metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"ScreenShareMetrics calculation failed: {str(e)}") from e
