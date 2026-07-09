from engine.behavior.models import CameraMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.utils import safe_divide, clamp, now_ms
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class CameraMetricsCalculator:
  """
  Calculates camera usage duration, toggles, and face visibility ratios.
  """

  @measure_latency("camera_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      meeting_duration_sec: float,
      camera_toggles_count: int = 0
  ) -> CameraMetrics:
    """Compute camera metrics given cumulative visibility features and presence duration."""
    try:
      # Total presence duration
      if features.join_time:
        end_ts = features.leave_time or features.last_activity or now_ms()
        presence_duration = max(0.0, float(end_ts - features.join_time) / 1000.0)
      else:
        presence_duration = max(meeting_duration_sec, features.visible_time)

      if presence_duration <= 0.0:
        presence_duration = meeting_duration_sec

      # Camera enabled duration is estimated or tracked via features.visible_time / camera_on state
      cam_enabled = max(0.0, float(features.visible_time))
      if cam_enabled > presence_duration and presence_duration > 0:
        cam_enabled = presence_duration

      cam_disabled = max(0.0, presence_duration - cam_enabled)

      toggles = max(camera_toggles_count, 0)
      # If camera toggled at least when turned on/off in metadata
      if toggles == 0 and features.camera_on:
        toggles = 1

      # Visible percentage: cam_enabled / presence_duration
      vis_pct = safe_divide(cam_enabled, presence_duration) if presence_duration > 0 else 0.0
      vis_pct = clamp(vis_pct, 0.0, 1.0)

      # Face visibility ratio: assuming visible_time reflects face visibility when camera is enabled
      # If visible_time <= cam_enabled, ratio = visible_time / cam_enabled
      face_ratio = safe_divide(features.visible_time, cam_enabled) if cam_enabled > 0 else (1.0 if features.camera_on else 0.0)
      face_ratio = clamp(face_ratio, 0.0, 1.0)

      return CameraMetrics(
          camera_enabled_duration=round(cam_enabled, 4),
          camera_disabled_duration=round(cam_disabled, 4),
          number_of_camera_toggles=toggles,
          visible_percentage=round(vis_pct, 4),
          face_visibility_ratio=round(face_ratio, 4)
      )

    except Exception as e:
      logger.error(f"Error calculating camera metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"CameraMetrics calculation failed: {str(e)}") from e
