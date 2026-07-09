"""
Pydantic V2 schemas for the SCIE Dynamic Weighting Engine.

Defines input payload structures, intermediate normalized quality scores, and the final
``DynamicWeightProfile`` consumed downstream by the Fusion Engine.

(`engine/weighting/schemas.py`)
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from engine.weighting.constants import (
    EvidenceAvailability, WeightingStrategyType,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
from engine.weighting.utils import now_ms


class UpstreamParticipantState(BaseModel):
  """Participant meeting context state retrieved from Redis."""
  participant_id: str = Field(..., description="Unique participant identifier")
  meeting_id: str = Field(..., description="Unique meeting identifier")
  track_id: Optional[str] = None
  speaker_id: Optional[str] = None
  camera_on: bool = True
  mic_on: bool = True
  screen_share: bool = False
  face_visible: bool = True
  voice_detected: bool = True
  transcript_available: bool = True
  emotion: Optional[str] = None
  gaze: Optional[str] = None
  language: Optional[str] = "en"
  visual_confidence: float = 0.85
  voice_confidence: float = 0.85
  transcript_confidence: float = 0.90
  behavior_confidence: float = 0.85
  conversation_confidence: float = 0.90
  identity_confidence: float = 0.90
  metadata_confidence: float = 0.95
  last_updated: int = Field(default_factory=now_ms)


class EvidencePayloads(BaseModel):
  """Container holding raw upstream evidence objects across all 7 domains."""
  visual_evidence: Optional[Dict[str, Any]] = None
  voice_evidence: Optional[Dict[str, Any]] = None
  transcript_evidence: Optional[Dict[str, Any]] = None
  conversation_evidence: Optional[Dict[str, Any]] = None
  behavior_evidence: Optional[Dict[str, Any]] = None
  identity_evidence: Optional[Dict[str, Any]] = None
  metadata_evidence: Optional[Dict[str, Any]] = None


class QualityScores(BaseModel):
  """Normalized [0.0, 1.0] quality evaluation scores across all 7 domains."""
  visual_quality: float = 1.0
  voice_quality: float = 1.0
  transcript_quality: float = 1.0
  conversation_quality: float = 1.0
  behavior_quality: float = 1.0
  identity_quality: float = 1.0
  metadata_quality: float = 1.0

  def get_overall_quality(self) -> float:
    """Compute average quality across active/non-zero quality domains."""
    vals = [
        self.visual_quality, self.voice_quality, self.transcript_quality,
        self.conversation_quality, self.behavior_quality, self.identity_quality,
        self.metadata_quality
    ]
    return sum(vals) / len(vals) if vals else 0.0


class DynamicWeightProfile(BaseModel):
  """Final structured output produced by the Dynamic Weighting Engine.

  Consumable by the downstream Fusion Engine to weight evidence scores precisely.
  """
  participant_id: str = Field(..., description="Target participant ID")
  meeting_id: str = Field(..., description="Target meeting ID")
  visual_weight: float = Field(..., ge=0.0, le=1.0)
  voice_weight: float = Field(..., ge=0.0, le=1.0)
  transcript_weight: float = Field(..., ge=0.0, le=1.0)
  conversation_weight: float = Field(..., ge=0.0, le=1.0)
  behavior_weight: float = Field(..., ge=0.0, le=1.0)
  identity_weight: float = Field(..., ge=0.0, le=1.0)
  metadata_weight: float = Field(..., ge=0.0, le=1.0)
  normalization_factor: float = Field(..., description="Multiplier used to normalize weights to 1.0")
  overall_quality: float = Field(..., ge=0.0, le=1.0)
  strategy_used: WeightingStrategyType = Field(default=WeightingStrategyType.DEFAULT)
  reasoning: List[str] = Field(default_factory=list, description="Diagnostic bullet points detailing weight adjustments")
  timestamp: int = Field(default_factory=now_ms)

  def as_dict(self) -> Dict[str, float]:
    """Return dictionary of domain weights mapped by domain string."""
    return {
        DOMAIN_VISUAL: self.visual_weight,
        DOMAIN_VOICE: self.voice_weight,
        DOMAIN_TRANSCRIPT: self.transcript_weight,
        DOMAIN_CONVERSATION: self.conversation_weight,
        DOMAIN_BEHAVIOR: self.behavior_weight,
        DOMAIN_IDENTITY: self.identity_weight,
        DOMAIN_METADATA: self.metadata_weight,
    }


class ParticipantWeightState(BaseModel):
  """Redis & MongoDB persistence model storing latest weight profile state."""
  participant_id: str
  meeting_id: str
  weights: Dict[str, float]
  strategy: str
  overall_quality: float
  reasons: List[str] = Field(default_factory=list)
  last_updated: int = Field(default_factory=now_ms)
