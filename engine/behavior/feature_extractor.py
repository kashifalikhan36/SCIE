from typing import Dict, Union, Optional
from engine.behavior.schemas import (
    BehaviorFeatures, VideoObservation, AudioObservation,
    TranscriptObservation, MetadataObservation
)
from engine.behavior.constants import (
    EVENT_JOIN, EVENT_LEAVE, EVENT_CAMERA_ON, EVENT_CAMERA_OFF,
    EVENT_MIC_ON, EVENT_MIC_OFF, EVENT_SCREEN_SHARE_ON, EVENT_SCREEN_SHARE_OFF
)
from engine.behavior.utils import now_ms, is_question
from engine.behavior.exceptions import FeatureExtractorError
from engine.behavior.logger import logger, measure_latency


class BehaviorFeatureExtractor:
  """
  Continuously extracts and updates behavioral features for meeting participants.

  Consumes observations from Audio, Video, Transcript, and Metadata engines
  and incrementally updates ``BehaviorFeatures`` in memory or state.
  """

  def __init__(self):
    # participant_id -> BehaviorFeatures
    self._features_cache: Dict[str, BehaviorFeatures] = {}
    # participant_id -> last timestamp seen in ms for time delta computation
    self._last_ts: Dict[str, int] = {}

  def get_or_create_features(self, participant_id: str) -> BehaviorFeatures:
    """Retrieve existing features or initialize a clean ``BehaviorFeatures`` instance."""
    if participant_id not in self._features_cache:
      self._features_cache[participant_id] = BehaviorFeatures(
          participant_id=participant_id,
          last_activity=now_ms()
      )
    return self._features_cache[participant_id]

  def load_features(self, features: BehaviorFeatures) -> None:
    """Load existing features into memory cache (e.g., when restoring from Redis)."""
    self._features_cache[features.participant_id] = features

  @measure_latency("feature_extractor.extract")
  def extract(
      self,
      observation: Union[VideoObservation, AudioObservation, TranscriptObservation, MetadataObservation]
  ) -> BehaviorFeatures:
    """Process an incoming observation and update the target participant's feature state."""
    try:
      pid = observation.participant_id
      if not pid:
        if isinstance(observation, VideoObservation):
          pid = f"track_{observation.track_id}"
        elif isinstance(observation, (AudioObservation, TranscriptObservation)):
          pid = f"speaker_{observation.speaker_id}"
        else:
          raise FeatureExtractorError("Observation lacks participant_id and cannot be resolved.")

      features = self.get_or_create_features(pid)
      ts = observation.timestamp or now_ms()

      # Compute time gap for presence/silent accounting if we have seen this participant before
      last_seen = self._last_ts.get(pid, ts)
      delta_sec = max(0.0, float(ts - last_seen) / 1000.0)
      # Clamp delta_sec to prevent huge jumps (e.g. max 60 seconds gap per tick)
      if delta_sec > 60.0:
        delta_sec = 60.0

      self._last_ts[pid] = ts
      features.last_activity = ts

      # If participant is present (has joined and not left), accumulate silent time when not actively speaking
      if features.join_time and not features.leave_time and delta_sec > 0.0:
        if isinstance(observation, AudioObservation) and observation.speech_duration > 0:
          # Part of the delta was speech
          silent_gap = max(0.0, delta_sec - observation.speech_duration)
          features.silent_time += silent_gap
        else:
          features.silent_time += delta_sec

      # Dispatch to specific handler
      if isinstance(observation, MetadataObservation):
        self._process_metadata(features, observation, ts)
      elif isinstance(observation, VideoObservation):
        self._process_video(features, observation, delta_sec)
      elif isinstance(observation, AudioObservation):
        self._process_audio(features, observation)
      elif isinstance(observation, TranscriptObservation):
        self._process_transcript(features, observation)

      logger.debug(f"Updated features for {pid}: speech={features.speech_time:.1f}s, turns={features.turn_count}")
      return features

    except Exception as e:
      logger.error(f"Failed to extract features: {str(e)}", exc_info=True)
      if isinstance(e, FeatureExtractorError):
        raise
      raise FeatureExtractorError(f"Unexpected error extracting features: {str(e)}") from e

  def _process_metadata(
      self, features: BehaviorFeatures, obs: MetadataObservation, ts: int
  ) -> None:
    if obs.event_type == EVENT_JOIN:
      if not features.join_time:
        features.join_time = ts
      features.leave_time = None
    elif obs.event_type == EVENT_LEAVE:
      features.leave_time = ts
    elif obs.event_type == EVENT_CAMERA_ON:
      features.camera_on = True
      features.camera_off = False
    elif obs.event_type == EVENT_CAMERA_OFF:
      features.camera_on = False
      features.camera_off = True
    elif obs.event_type == EVENT_MIC_ON:
      features.mic_on = True
      features.mic_off = False
    elif obs.event_type == EVENT_MIC_OFF:
      features.mic_on = False
      features.mic_off = True
    elif obs.event_type == EVENT_SCREEN_SHARE_ON:
      features.screen_share = True
    elif obs.event_type == EVENT_SCREEN_SHARE_OFF:
      features.screen_share = False

  def _process_video(
      self, features: BehaviorFeatures, obs: VideoObservation, delta_sec: float
  ) -> None:
    if obs.track_id:
      features.track_id = obs.track_id
    if obs.visibility or features.camera_on:
      if delta_sec > 0.0:
        features.visible_time += delta_sec
    if obs.emotion_label:
      features.emotion = obs.emotion_label.lower()
    if obs.gaze_direction:
      features.gaze_direction = obs.gaze_direction.lower()

  def _process_audio(self, features: BehaviorFeatures, obs: AudioObservation) -> None:
    if obs.speaker_id:
      features.speaker_id = obs.speaker_id
    if obs.speech_duration > 0.0:
      features.speech_time += obs.speech_duration
      if obs.speech_duration > features.longest_monologue:
        features.longest_monologue = obs.speech_duration
    if obs.language:
      features.language = obs.language

  def _process_transcript(
      self, features: BehaviorFeatures, obs: TranscriptObservation
  ) -> None:
    if obs.speaker_id:
      features.speaker_id = obs.speaker_id
    if obs.word_count > 0:
      features.word_count += obs.word_count
    if obs.is_final:
      features.turn_count += 1
      # Check question or answer
      if obs.is_question or is_question(obs.text):
        features.question_count += 1
      else:
        features.response_count += 1
