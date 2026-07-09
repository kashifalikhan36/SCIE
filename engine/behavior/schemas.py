from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Input Observation Event Wrappers
# ──────────────────────────────────────────────────────────────────────────────

class VideoObservation(BaseModel):
  """Video Engine observation of face tracking and visibility."""
  meeting_id: str
  track_id: str
  participant_id: Optional[str] = None
  timestamp: int                 # Epoch ms
  visibility: bool
  face_confidence: float = 1.0
  emotion_label: Optional[str] = None
  gaze_direction: Optional[str] = None


class AudioObservation(BaseModel):
  """Audio Engine observation of speech duration and diarization."""
  meeting_id: str
  speaker_id: str
  participant_id: Optional[str] = None
  timestamp: int                 # Epoch ms
  speech_start: float            # Seconds relative to meeting or window
  speech_end: float              # Seconds relative to meeting or window
  speech_duration: float
  language: str = "en"


class TranscriptObservation(BaseModel):
  """Transcript Engine observation of speech utterances and turn text."""
  meeting_id: str
  speaker_id: str
  participant_id: Optional[str] = None
  timestamp: int                 # Epoch ms
  text: str
  start_time: float
  end_time: float
  duration: float
  word_count: int
  is_final: bool = True
  is_question: bool = False


class MetadataObservation(BaseModel):
  """Meeting Metadata observation (join, leave, camera/mic/screen toggles)."""
  meeting_id: str
  participant_id: str
  timestamp: int                 # Epoch ms
  event_type: str                # JOIN, LEAVE, CAMERA_ON, CAMERA_OFF, MIC_ON, MIC_OFF, SCREEN_SHARE_ON, SCREEN_SHARE_OFF
  display_name: Optional[str] = None
  platform_role: Optional[str] = None
  extra_data: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Behavior Features (Observed / Extracted continuously)
# ──────────────────────────────────────────────────────────────────────────────

class BehaviorFeatures(BaseModel):
  """Continuous extracted behavioral features for a participant.

  These are raw observed and incremental analytical features, not final decisions.
  """
  participant_id: str
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  join_time: Optional[int] = None           # Epoch ms
  leave_time: Optional[int] = None          # Epoch ms
  camera_on: bool = False
  camera_off: bool = True
  mic_on: bool = False
  mic_off: bool = True
  screen_share: bool = False
  visible_time: float = 0.0                 # Total seconds face/camera visible
  speech_time: float = 0.0                  # Total seconds speaking
  silent_time: float = 0.0                  # Total seconds silent while present
  word_count: int = 0
  turn_count: int = 0
  response_count: int = 0
  question_count: int = 0
  interruptions: int = 0
  average_response_time: float = 0.0
  longest_monologue: float = 0.0
  language: str = "en"
  emotion: str = "neutral"
  gaze_direction: str = "looking_at_screen"
  last_activity: int = 0                    # Epoch ms of latest observed event


# ──────────────────────────────────────────────────────────────────────────────
# Domain Metric Summaries (Structured API objects)
# ──────────────────────────────────────────────────────────────────────────────

class SpeakingMetricsSummary(BaseModel):
  total_speaking_duration: float = 0.0
  average_speaking_duration: float = 0.0
  longest_speaking_turn: float = 0.0
  shortest_speaking_turn: float = 0.0
  speaking_percentage: float = 0.0
  number_of_speaking_turns: int = 0
  average_words_per_minute: float = 0.0
  average_pause_duration: float = 0.0


class ResponseMetricsSummary(BaseModel):
  average_response_delay: float = 0.0
  fastest_response: float = 0.0
  slowest_response: float = 0.0
  response_consistency: float = 0.0
  average_answer_length: float = 0.0
  average_reply_duration: float = 0.0


class InterruptionMetricsSummary(BaseModel):
  interruption_count: int = 0
  interruption_frequency: float = 0.0
  interrupted_participants: List[str] = Field(default_factory=list)
  interrupting_participants: List[str] = Field(default_factory=list)


class ParticipationMetricsSummary(BaseModel):
  participation_percentage: float = 0.0
  active_time: float = 0.0
  idle_time: float = 0.0
  total_meeting_presence: float = 0.0
  active_conversation_ratio: float = 0.0
  speaking_to_listening_ratio: float = 0.0


class CameraMetricsSummary(BaseModel):
  camera_enabled_duration: float = 0.0
  camera_disabled_duration: float = 0.0
  number_of_camera_toggles: int = 0
  visible_percentage: float = 0.0
  face_visibility_ratio: float = 0.0


class ScreenShareMetricsSummary(BaseModel):
  total_screen_share_duration: float = 0.0
  number_of_screen_share_sessions: int = 0
  first_screen_share_time: Optional[float] = None
  latest_screen_share_time: Optional[float] = None


class EngagementMetricsSummary(BaseModel):
  engagement_score: float = Field(default=0.0, ge=0.0, le=1.0)
  engagement_level: str = "LOW"
  component_scores: Dict[str, float] = Field(default_factory=dict)


class EmotionMetricsSummary(BaseModel):
  neutral_percentage: float = 100.0
  happy_percentage: float = 0.0
  confused_percentage: float = 0.0
  surprised_percentage: float = 0.0


class GazeMetricsSummary(BaseModel):
  looking_at_screen_percentage: float = 100.0
  looking_away_percentage: float = 0.0
  looking_down_percentage: float = 0.0
  attention_ratio: float = 1.0


# ──────────────────────────────────────────────────────────────────────────────
# Behavioral Timeline Entry
# ──────────────────────────────────────────────────────────────────────────────

class BehaviorTimelineEntry(BaseModel):
  """A single event in a participant's chronological behavioral timeline."""
  entry_id: str
  meeting_id: str
  participant_id: str
  timestamp_ms: int
  formatted_time: str            # e.g., "00:04 Camera On" or "HH:MM:SS Description"
  event_type: str                # JOIN, CAMERA_ON, SPEAKING_START, etc.
  description: str               # Human-readable timeline milestone
  metadata: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Redis Live State Schema
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantBehaviorState(BaseModel):
  """Live participant behavior state cached in Azure Cache for Redis."""
  participant_id: str
  current_behavior: str = "idle"            # "speaking", "listening", "idle", "screen_sharing"
  latest_metrics: Dict[str, Any] = Field(default_factory=dict)
  engagement_score: float = 0.0
  camera_status: bool = False
  screen_share: bool = False
  speaking_ratio: float = 0.0
  last_updated: int                         # Epoch ms


# ──────────────────────────────────────────────────────────────────────────────
# Final Output Evidence Schema
# ──────────────────────────────────────────────────────────────────────────────

class BehaviorEvidence(BaseModel):
  """Canonical behavioral evidence output emitted by Behavior Engine.

  Consumed directly by downstream engines:
  - Participant Association Engine
  - Conversation Reasoning Engine (GPT-5.5)
  - Evidence Fusion Engine
  """
  evidence_id: str
  meeting_id: str
  participant_id: str
  speaking_ratio: float = Field(..., ge=0.0, le=1.0)
  speech_duration: float = Field(..., ge=0.0)
  response_time: float = Field(default=0.0, ge=0.0)
  question_count: int = 0
  answer_count: int = 0
  interruptions: int = 0
  engagement_score: float = Field(..., ge=0.0, le=1.0)
  camera_ratio: float = Field(..., ge=0.0, le=1.0)
  screen_share_ratio: float = Field(..., ge=0.0, le=1.0)
  emotion_summary: Dict[str, float] = Field(default_factory=dict)
  gaze_summary: Dict[str, float] = Field(default_factory=dict)
  behavior_confidence: float = Field(..., ge=0.0, le=1.0)
  timestamp: int                            # Epoch ms
