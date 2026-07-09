from typing import Union, Optional
from engine.behavior.schemas import (
    VideoObservation, AudioObservation, TranscriptObservation,
    MetadataObservation, BehaviorEvidence, BehaviorFeatures
)
from engine.behavior.feature_extractor import BehaviorFeatureExtractor
from engine.behavior.speaking_metrics import SpeakingMetricsCalculator
from engine.behavior.response_metrics import ResponseMetricsCalculator
from engine.behavior.interruption_metrics import InterruptionMetricsCalculator
from engine.behavior.participation_metrics import ParticipationMetricsCalculator
from engine.behavior.camera_metrics import CameraMetricsCalculator
from engine.behavior.screen_share_metrics import ScreenShareMetricsCalculator
from engine.behavior.engagement_metrics import EngagementMetricsCalculator
from engine.behavior.emotion_metrics import EmotionMetricsCalculator
from engine.behavior.gaze_metrics import GazeMetricsCalculator
from engine.behavior.timeline_builder import BehaviorTimelineBuilder
from engine.behavior.evidence_provider import BehaviorEvidenceProvider
from engine.behavior.participant_state import BehaviorStateManager
from engine.behavior.storage import BehaviorStorageManager
from engine.behavior.constants import EVENT_SPEAKING_START, EVENT_CAMERA_ON, EVENT_SCREEN_SHARE_ON
from engine.behavior.exceptions import PipelineExecutionError
from engine.behavior.logger import logger, measure_latency


class BehaviorPipeline:
  """Orchestrates the end-to-end Behavior Evidence generation and observation flow.

  Data flow::
      Observation (Audio / Video / Transcript / Metadata)
        └─ BehaviorFeatureExtractor       (accumulate features & presence stats)
        └─ Domain Metric Calculators      (Speaking, Response, Interruption, Participation, Camera, Screen, Engagement, Emotion, Gaze)
        └─ BehaviorTimelineBuilder        (check & log chronological milestones)
        └─ BehaviorEvidenceProvider       (synthesize canonical BehaviorEvidence)
        └─ BehaviorStateManager           (update live Redis state & meeting behaviors)
        └─ BehaviorStorageManager         (persist all 5 MongoDB history collections)
  """

  def __init__(self):
    self._extractor = BehaviorFeatureExtractor()
    self._speaking_calc = SpeakingMetricsCalculator()
    self._response_calc = ResponseMetricsCalculator()
    self._interruption_calc = InterruptionMetricsCalculator()
    self._participation_calc = ParticipationMetricsCalculator()
    self._camera_calc = CameraMetricsCalculator()
    self._screen_calc = ScreenShareMetricsCalculator()
    self._engagement_calc = EngagementMetricsCalculator()
    self._emotion_calc = EmotionMetricsCalculator()
    self._gaze_calc = GazeMetricsCalculator()
    self._timeline_builder = BehaviorTimelineBuilder()
    self._provider = BehaviorEvidenceProvider()
    self._state_mgr = BehaviorStateManager()
    self._storage = BehaviorStorageManager()

  @measure_latency("pipeline.process")
  async def process(
      self,
      observation: Union[VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation],
      meeting_duration_sec: float = 3600.0,
      turn_durations: Optional[list] = None,
      pause_durations: Optional[list] = None,
      response_delays: Optional[list] = None,
      reply_durations: Optional[list] = None,
      reply_words: Optional[list] = None
  ) -> Optional[BehaviorEvidence]:
    """Process an incoming observation, update metrics, and emit structured ``BehaviorEvidence``."""
    try:
      # 1. Extract and update cumulative features
      features = self._extractor.extract(observation)
      pid = features.participant_id

      # If Video Observation has emotion/gaze, record to specialized accumulators
      if isinstance(observation, VideoObservation):
        if observation.emotion_label:
          self._emotion_calc.record_emotion(pid, observation.emotion_label)
        if observation.gaze_direction:
          self._gaze_calc.record_gaze(pid, observation.gaze_direction)

      # 2. Compute domain metrics
      speaking = self._speaking_calc.calculate(features, meeting_duration_sec, turn_durations, pause_durations)
      response = self._response_calc.calculate(features, response_delays, reply_durations, reply_words)
      interruption = self._interruption_calc.calculate(features, meeting_duration_sec)
      participation = self._participation_calc.calculate(features, meeting_duration_sec)
      camera = self._camera_calc.calculate(features, meeting_duration_sec)
      screen = self._screen_calc.calculate(features, meeting_duration_sec)
      emotion = self._emotion_calc.calculate(features)
      gaze = self._gaze_calc.calculate(features)
      engagement = self._engagement_calc.calculate(features, speaking, response, camera, screen, meeting_duration_sec)

      # 3. Check / update timeline milestones
      if isinstance(observation, AudioObservation) and observation.speech_duration > 0 and features.turn_count == 1:
        entry = self._timeline_builder.add_entry(
            meeting_id=observation.meeting_id,
            participant_id=pid,
            event_type=EVENT_SPEAKING_START,
            description="Started Speaking",
            timestamp_ms=observation.timestamp
        )
        await self._storage.save_timeline_entry(entry)

      elif isinstance(observation, MetadataObservation):
        entry = self._timeline_builder.add_entry(
            meeting_id=observation.meeting_id,
            participant_id=pid,
            event_type=observation.event_type,
            description=f"Event: {observation.event_type}",
            timestamp_ms=observation.timestamp,
            metadata=observation.extra_data
        )
        await self._storage.save_timeline_entry(entry)

      # 4. Generate canonical BehaviorEvidence
      evidence = self._provider.provide(
          features=features,
          speaking=speaking,
          response=response,
          interruption=interruption,
          participation=participation,
          camera=camera,
          screen=screen,
          engagement=engagement,
          emotion=emotion,
          gaze=gaze,
          meeting_id=observation.meeting_id
      )

      # 5. Save live state to Azure Cache for Redis
      await self._state_mgr.save_state(features, evidence)

      # 6. Save historical records to MongoDB
      await self._storage.save_event(
          meeting_id=observation.meeting_id,
          participant_id=pid,
          event_type=observation.__class__.__name__,
          payload={"evidence_id": evidence.evidence_id, "timestamp": evidence.timestamp},
          timestamp=observation.timestamp
      )
      await self._storage.save_metrics_snapshot(evidence)
      await self._storage.save_engagement_history(
          meeting_id=observation.meeting_id,
          participant_id=pid,
          engagement_score=engagement.engagement_score,
          engagement_level=engagement.engagement_level,
          component_scores=engagement.component_scores,
          timestamp=observation.timestamp
      )

      logger.info(f"Processed behavior for {pid}: engagement={engagement.engagement_level} ({engagement.engagement_score:.2f})")
      return evidence

    except Exception as e:
      logger.error(f"BehaviorPipeline processing failed: {str(e)}", exc_info=True)
      if isinstance(e, PipelineExecutionError):
        raise
      raise PipelineExecutionError(f"Unexpected pipeline failure: {str(e)}") from e
