from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from engine.behavior.constants import ENGAGEMENT_LOW


@dataclass
class SpeakingMetrics:
  """Calculated speaking metrics for a participant."""
  total_speaking_duration: float = 0.0
  average_speaking_duration: float = 0.0
  longest_speaking_turn: float = 0.0
  shortest_speaking_turn: float = 0.0
  speaking_percentage: float = 0.0
  number_of_speaking_turns: int = 0
  average_words_per_minute: float = 0.0
  average_pause_duration: float = 0.0


@dataclass
class ResponseMetrics:
  """Calculated response metrics based on transcript timestamps."""
  average_response_delay: float = 0.0
  fastest_response: float = 0.0
  slowest_response: float = 0.0
  response_consistency: float = 0.0      # Inverse of variance (or standard deviation)
  average_answer_length_words: float = 0.0
  average_reply_duration: float = 0.0


@dataclass
class InterruptionMetrics:
  """Calculated interruption metrics for a participant."""
  interruption_count: int = 0
  interruption_frequency: float = 0.0    # Interruptions per hour of meeting
  interrupted_participants: List[str] = field(default_factory=list)
  interrupting_participants: List[str] = field(default_factory=list)


@dataclass
class ParticipationMetrics:
  """Calculated participation presence and ratio metrics."""
  participation_percentage: float = 0.0  # active_time / meeting_duration
  active_time: float = 0.0
  idle_time: float = 0.0
  total_meeting_presence: float = 0.0
  active_conversation_ratio: float = 0.0 # speech_time / presence_time
  speaking_to_listening_ratio: float = 0.0 # speech_time / silent_time


@dataclass
class CameraMetrics:
  """Calculated camera toggles and visibility metrics."""
  camera_enabled_duration: float = 0.0
  camera_disabled_duration: float = 0.0
  number_of_camera_toggles: int = 0
  visible_percentage: float = 0.0        # camera_enabled / total_meeting_presence
  face_visibility_ratio: float = 0.0     # face_tracking_visible / camera_enabled


@dataclass
class ScreenShareMetrics:
  """Calculated screen sharing duration and session metrics."""
  total_screen_share_duration: float = 0.0
  number_of_screen_share_sessions: int = 0
  first_screen_share_time: Optional[float] = None
  latest_screen_share_time: Optional[float] = None


@dataclass
class EngagementMetrics:
  """Calculated engagement score and level."""
  engagement_score: float = 0.0
  engagement_level: str = ENGAGEMENT_LOW
  component_scores: Dict[str, float] = field(default_factory=dict)


@dataclass
class EmotionMetrics:
  """Aggregated emotion percentages."""
  neutral_percentage: float = 100.0
  happy_percentage: float = 0.0
  confused_percentage: float = 0.0
  surprised_percentage: float = 0.0


@dataclass
class GazeMetrics:
  """Aggregated gaze and attention metrics."""
  looking_at_screen_percentage: float = 100.0
  looking_away_percentage: float = 0.0
  looking_down_percentage: float = 0.0
  attention_ratio: float = 1.0


@dataclass
class InterruptionEvent:
  """Record of a single detected interruption between two participants."""
  meeting_id: str
  interrupter_id: str
  interrupted_id: str
  timestamp_ms: int
  interrupter_turn_duration: float
