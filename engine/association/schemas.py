from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union


# ──────────────────────────────────────────────────────────────────────────────
# Input Event & Metadata Schemas
# ──────────────────────────────────────────────────────────────────────────────

class MeetingMetadata(BaseModel):
  """Meeting profile metadata from DOM / extension / calendar."""
  meeting_id: str
  candidate_name: Optional[str] = None
  display_name: Optional[str] = None
  email: Optional[str] = None
  meeting_title: Optional[str] = None
  calendar_info: Optional[Dict[str, Any]] = None
  nicknames: List[str] = Field(default_factory=list)


class MeetingEvent(BaseModel):
  """Real-time DOM event triggered by participant actions."""
  meeting_id: str
  event_type: str = Field(..., description="e.g. 'join', 'leave', 'mic_on', 'mic_off', 'camera_on', 'camera_off', 'screen_share'")
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  display_name: Optional[str] = None
  email: Optional[str] = None
  timestamp: int = Field(..., description="Epoch milliseconds")


# ──────────────────────────────────────────────────────────────────────────────
# Matcher Evidence Outputs
# Each matcher produces a typed evidence object containing normalized score,
# confidence, and human/machine-readable reasons.
# ──────────────────────────────────────────────────────────────────────────────

class MetadataMatchEvidence(BaseModel):
  """Evidence produced by MetadataMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  matched_name: Optional[str] = None
  matched_email: Optional[str] = None
  similarity_metric: str = Field(default="rapidfuzz")


class TranscriptMatchEvidence(BaseModel):
  """Evidence produced by TranscriptMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  extracted_name: Optional[str] = None
  is_self_intro: bool = False
  is_addressed: bool = False


class SpeakerMatchEvidence(BaseModel):
  """Evidence produced by SpeakerMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  speaker_id: Optional[str] = None
  voice_similarity: float = 0.0


class TrackMatchEvidence(BaseModel):
  """Evidence produced by TrackMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  track_id: Optional[str] = None
  visual_similarity: float = 0.0
  visibility: bool = True


class TimelineMatchEvidence(BaseModel):
  """Evidence produced by TimelineMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  co_occurring_events: List[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Core Unified Identity Models
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantIdentity(BaseModel):
  """Internal unified participant object constructed by ParticipantBuilder."""
  participant_id: str
  display_name: Optional[str] = None
  email: Optional[str] = None
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  metadata_score: float = 0.0
  transcript_score: float = 0.0
  speaker_score: float = 0.0
  track_score: float = 0.0
  timeline_score: float = 0.0
  association_score: float = 0.0
  association_confidence: float = 0.0
  reasons: List[str] = Field(default_factory=list)
  timestamp: int


class ParticipantIdentityState(BaseModel):
  """Live participant identity state cached in Azure Cache for Redis."""
  participant_id: str
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  display_name: Optional[str] = None
  email: Optional[str] = None
  association_score: float = 0.0
  association_confidence: float = 0.0
  history: List[Dict[str, Any]] = Field(default_factory=list)
  last_updated: int


class ParticipantAssociation(BaseModel):
  """Canonical final output object emitted by the Participant Association Engine.

  Consumed directly by downstream engines (Behavior Engine, Conversation Reasoning,
  Evidence Fusion Engine, Confidence Engine).
  """
  meeting_id: str
  participant_id: str
  display_name: Optional[str] = None
  email: Optional[str] = None
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  association_score: float = Field(..., ge=0.0, le=1.0)
  association_confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  timestamp: int
