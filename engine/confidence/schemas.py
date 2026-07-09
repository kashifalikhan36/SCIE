"""
Pydantic V2 Schemas for the SCIE Confidence Engine (`engine/confidence/schemas.py`).

Defines structured interfaces across:
- `Evidence`: Validated input from all upstream engines.
- `ParticipantConfidence`: Live rolling state inside Azure Cache for Redis.
- `ConfidenceResult`: Final structured output consumed by Dashboard/Explanation Engine.
- `ConfidenceEvent`: Discrete event log across decay, recovery, and hardware triggers.
"""
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from engine.confidence.constants import ConfidenceTrend


class Evidence(BaseModel):
  """Standardized evidence object emitted by any upstream SCIE engine."""
  model_config = ConfigDict(extra="allow", populate_by_name=True)

  participant_id: str = Field(..., description="Unique identifier of the meeting participant")
  source: str = Field(..., description="Evidence source identifier (face, voice, identity, conversation, behavior, transcript, emotion, gaze)")
  score: float = Field(..., description="Raw analytical score produced by upstream engine")
  confidence: float = Field(..., description="Upstream signal confidence bound [0.0, 1.0]")
  reason: str = Field(default="Evidence generated upstream", description="Human-readable reason or diagnostic tag")
  timestamp: float = Field(..., description="High-precision UTC epoch timestamp of evidence emission")
  metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional extra diagnostic details")


class ParticipantConfidence(BaseModel):
  """Comprehensive rolling state for one participant in a meeting."""
  model_config = ConfigDict(extra="ignore")

  participant_id: str = Field(..., description="Unique identifier of the participant")
  meeting_id: str = Field(..., description="Unique identifier of the meeting session")
  current_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Current overall confidence [0.0, 1.0]")
  previous_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence before latest turn")
  highest_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Peak overall confidence reached across meeting")
  lowest_confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Lowest overall confidence recorded across meeting")
  confidence_history: List[Dict[str, Any]] = Field(default_factory=list, description="Chronological timeline of past confidence checkpoints")
  last_updated: float = Field(..., description="Timestamp of most recent state recalculation")
  active_evidence: Dict[str, float] = Field(default_factory=dict, description="Map of active domain -> normalized contribution")
  missing_evidence: List[str] = Field(default_factory=list, description="List of recognized domains currently missing or timed out")


class ConfidenceResult(BaseModel):
  """Unified structured output consumed by Dashboard, Explanation Engine, and Candidate Selection Engine."""
  model_config = ConfigDict(extra="ignore")

  participant_id: str = Field(..., description="Participant unique identifier")
  meeting_id: str = Field(..., description="Meeting session identifier")
  overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Final overall confidence [0.0, 1.0]")
  evidence_breakdown: Dict[str, float] = Field(default_factory=dict, description="Per-source normalized score contribution")
  active_weights: Dict[str, float] = Field(default_factory=dict, description="Dynamically adjusted weights applied during evaluation")
  reasons: List[str] = Field(default_factory=list, description="Auditable bullet points justifying confidence shifts and dynamic weighting")
  trend: str = Field(default=ConfidenceTrend.STABLE.value, description="Trajectory classification (UPWARD, DOWNWARD, STABLE, RECOVERING)")
  timestamp: float = Field(..., description="Evaluation timestamp")


class ConfidenceEvent(BaseModel):
  """Audit log entry capturing discrete state shifts, decay triggers, and recovery events."""
  model_config = ConfigDict(extra="ignore")

  event_id: str = Field(..., description="Unique event identifier")
  meeting_id: str = Field(..., description="Meeting session identifier")
  participant_id: str = Field(..., description="Participant unique identifier")
  event_type: str = Field(..., description="Type of event (DECAY_STARTED, RECOVERY_STARTED, CAMERA_OFF, HIGH_CONFIDENCE)")
  old_confidence: float = Field(..., ge=0.0, le=1.0)
  new_confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  timestamp: float = Field(...)
