from engine.behavior.models import EngagementMetrics, SpeakingMetrics, ResponseMetrics, CameraMetrics, ScreenShareMetrics
from engine.behavior.schemas import BehaviorFeatures
from engine.behavior.config import behavior_config
from engine.behavior.constants import ENGAGEMENT_LOW, ENGAGEMENT_MEDIUM, ENGAGEMENT_HIGH
from engine.behavior.utils import safe_divide, clamp
from engine.behavior.exceptions import MetricCalculationError
from engine.behavior.logger import logger, measure_latency


class EngagementMetricsCalculator:
  """
  Calculates overall analytical engagement score and categorical engagement level.

  Zero GPT usage. Pure analytical weighted formula across:
  - Speaking frequency / percentage
  - Camera visibility
  - Transcript activity
  - Response speed
  - Screen sharing activity
  """

  @measure_latency("engagement_metrics.calculate")
  def calculate(
      self,
      features: BehaviorFeatures,
      speaking_metrics: SpeakingMetrics,
      response_metrics: ResponseMetrics,
      camera_metrics: CameraMetrics,
      screen_metrics: ScreenShareMetrics,
      meeting_duration_sec: float
  ) -> EngagementMetrics:
    """Compute weighted analytical engagement score and categorize into LOW/MEDIUM/HIGH."""
    try:
      # 1. Speaking score: normalized against a target 20% speaking share (so 20%+ = 1.0)
      spk_score = clamp(speaking_metrics.speaking_percentage / 0.20, 0.0, 1.0)

      # 2. Camera score: visible percentage
      cam_score = clamp(camera_metrics.visible_percentage, 0.0, 1.0)

      # 3. Transcript activity score: based on turns and questions asked
      # E.g. at least 1 turn per 5 minutes = active
      mtg_mins = max(1.0, safe_divide(meeting_duration_sec, 60.0))
      turn_rate = safe_divide(float(features.turn_count + features.question_count), mtg_mins)
      trans_score = clamp(turn_rate / 0.5, 0.0, 1.0)  # 0.5 turns/min = 1.0

      # 4. Response speed score: inversely proportional to response delay up to SLOW_RESPONSE_THRESHOLD
      if response_metrics.average_response_delay > 0:
        delay_penalty = safe_divide(
            response_metrics.average_response_delay,
            behavior_config.SLOW_RESPONSE_THRESHOLD_SEC,
            default=1.0
        )
        resp_score = clamp(1.0 - delay_penalty, 0.0, 1.0)
      else:
        resp_score = 1.0 if features.turn_count > 0 else 0.5

      # 5. Screen sharing score: 1.0 if any screen sharing occurred, else 0.0
      screen_score = 1.0 if (screen_metrics.total_screen_share_duration > 0 or features.screen_share) else 0.0

      # Weighted combination
      w_spk = behavior_config.WEIGHT_SPEAKING
      w_cam = behavior_config.WEIGHT_CAMERA
      w_trans = behavior_config.WEIGHT_TRANSCRIPT
      w_resp = behavior_config.WEIGHT_RESPONSE
      w_scr = behavior_config.WEIGHT_SCREEN

      # Normalize weights in case they don't sum to exactly 1.0
      total_weight = w_spk + w_cam + w_trans + w_resp + w_scr
      if total_weight <= 0:
        total_weight = 1.0

      raw_score = (
          spk_score * w_spk +
          cam_score * w_cam +
          trans_score * w_trans +
          resp_score * w_resp +
          screen_score * w_scr
      ) / total_weight

      score = round(clamp(raw_score, 0.0, 1.0), 4)

      # Determine categorical level
      if score >= behavior_config.ENGAGEMENT_HIGH_THRESHOLD:
        level = ENGAGEMENT_HIGH
      elif score >= behavior_config.ENGAGEMENT_MEDIUM_THRESHOLD:
        level = ENGAGEMENT_MEDIUM
      else:
        level = ENGAGEMENT_LOW

      component_scores = {
          "speaking": round(spk_score, 4),
          "camera": round(cam_score, 4),
          "transcript": round(trans_score, 4),
          "response": round(resp_score, 4),
          "screen_share": round(screen_score, 4)
      }

      return EngagementMetrics(
          engagement_score=score,
          engagement_level=level,
          component_scores=component_scores
      )

    except Exception as e:
      logger.error(f"Error calculating engagement metrics for {features.participant_id}: {str(e)}")
      raise MetricCalculationError(f"EngagementMetrics calculation failed: {str(e)}") from e
