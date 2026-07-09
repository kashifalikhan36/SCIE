from typing import Dict, Any
from engine.behavior.schemas import BehaviorEvidence, BehaviorFeatures
from engine.behavior.models import (
    SpeakingMetrics, ResponseMetrics, InterruptionMetrics,
    ParticipationMetrics, CameraMetrics, ScreenShareMetrics,
    EngagementMetrics, EmotionMetrics, GazeMetrics
)
from engine.behavior.utils import generate_evidence_id, clamp, safe_divide, now_ms
from engine.behavior.exceptions import BehaviorEngineException
from engine.behavior.logger import logger, measure_latency


class BehaviorEvidenceProvider:
  """
  Synthesizes all behavioral domain metrics into the unified canonical ``BehaviorEvidence`` object.
  """

  @measure_latency("evidence_provider.provide")
  def provide(
      self,
      features: BehaviorFeatures,
      speaking: SpeakingMetrics,
      response: ResponseMetrics,
      interruption: InterruptionMetrics,
      participation: ParticipationMetrics,
      camera: CameraMetrics,
      screen: ScreenShareMetrics,
      engagement: EngagementMetrics,
      emotion: EmotionMetrics,
      gaze: GazeMetrics,
      meeting_id: str
  ) -> BehaviorEvidence:
    """Generate canonical ``BehaviorEvidence`` for downstream fusion engines."""
    try:
      # Estimate confidence based on signal richness and duration
      # More active time and observed turns increase confidence up to 0.95+
      base_conf = 0.50
      if participation.total_meeting_presence >= 60.0:
        base_conf += 0.20
      elif participation.total_meeting_presence >= 10.0:
        base_conf += 0.10

      if features.turn_count > 0 or features.speech_time > 0:
        base_conf += 0.15
      if features.visible_time > 0 or features.camera_on:
        base_conf += 0.10
      if features.word_count > 10:
        base_conf += 0.05

      confidence = round(clamp(base_conf, 0.0, 1.0), 4)

      emotion_dict = {
          "neutral": emotion.neutral_percentage,
          "happy": emotion.happy_percentage,
          "confused": emotion.confused_percentage,
          "surprised": emotion.surprised_percentage
      }

      gaze_dict = {
          "looking_at_screen": gaze.looking_at_screen_percentage,
          "looking_away": gaze.looking_away_percentage,
          "looking_down": gaze.looking_down_percentage,
          "attention_ratio": gaze.attention_ratio
      }

      evidence = BehaviorEvidence(
          evidence_id=generate_evidence_id(),
          meeting_id=meeting_id,
          participant_id=features.participant_id,
          speaking_ratio=round(clamp(speaking.speaking_percentage, 0.0, 1.0), 4),
          speech_duration=round(max(0.0, float(features.speech_time)), 4),
          response_time=round(max(0.0, float(response.average_response_delay)), 4),
          question_count=max(0, int(features.question_count)),
          answer_count=max(0, int(features.response_count)),
          interruptions=max(0, int(interruption.interruption_count)),
          engagement_score=round(clamp(engagement.engagement_score, 0.0, 1.0), 4),
          camera_ratio=round(clamp(camera.visible_percentage, 0.0, 1.0), 4),
          screen_share_ratio=round(clamp(safe_divide(screen.total_screen_share_duration, participation.total_meeting_presence), 0.0, 1.0), 4),
          emotion_summary=emotion_dict,
          gaze_summary=gaze_dict,
          behavior_confidence=confidence,
          timestamp=now_ms()
      )

      return evidence

    except Exception as e:
      logger.error(f"Failed to generate BehaviorEvidence for {features.participant_id}: {str(e)}")
      raise BehaviorEngineException(f"BehaviorEvidence synthesis failed: {str(e)}") from e
