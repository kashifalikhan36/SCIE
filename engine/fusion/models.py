"""
Internal dataclasses and models for the Evidence Fusion Engine (`engine/fusion/`).

Used by analytical modules (weighting, scoring, confidence computation, and aggregation)
to pass structured calculations without incurring Pydantic overhead during internal loops.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any
from engine.fusion.constants import EvidenceStatus


@dataclass
class WeightedEvidenceItem:
  """Internal representation of a scored and weighted domain evidence item."""
  domain: str
  raw_score: float = 0.0
  normalized_score: float = 0.0
  reliability: float = 1.0
  status: EvidenceStatus = EvidenceStatus.AVAILABLE
  age_seconds: float = 0.0
  freshness_multiplier: float = 1.0
  effective_weight: float = 0.0
  effective_score: float = 0.0
  reasons: List[str] = field(default_factory=list)


@dataclass
class ConfidenceComputationContext:
  """Context passed into the ConfidenceEngine to calculate multi-signal confidence."""
  participant_id: str
  meeting_id: str
  active_domains: List[str] = field(default_factory=list)
  domain_scores: Dict[str, float] = field(default_factory=dict)
  domain_reliabilities: Dict[str, float] = field(default_factory=dict)
  state_age_seconds: float = 0.0
  update_count: int = 1
  has_identity: bool = False
  has_visual: bool = False
  has_voice: bool = False
  has_behavior: bool = False
  has_conversation: bool = False


@dataclass
class AggregationBufferItem:
  """Wrapper around incoming evidence during windowed aggregation or deduplication checks."""
  item_id: str
  timestamp: int
  source_type: str
  participant_id: str
  score: float
  reliability: float
  status: EvidenceStatus
  payload: Dict[str, Any] = field(default_factory=dict)
