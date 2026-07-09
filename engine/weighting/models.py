"""
Internal dataclasses for zero-overhead analytical evaluation in the Dynamic Weighting Engine.

(`engine/weighting/models.py`)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from engine.weighting.constants import EvidenceAvailability, WeightingStrategyType


@dataclass
class DomainQualityMetrics:
  """Raw metrics extracted from incoming evidence dicts before normalization."""
  domain: str
  confidence: float = 1.0
  reliability: float = 1.0
  age_ms: int = 0
  extra_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainWeightItem:
  """Internal mutable state representing a single domain during rule evaluation."""
  domain: str
  raw_base_weight: float
  availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE
  quality_score: float = 1.0
  adjusted_weight: float = 0.0
  adjustment_reasons: List[str] = field(default_factory=list)


@dataclass
class StrategyEvaluationContext:
  """Context passed into rules and strategy selection engines."""
  meeting_id: str
  participant_id: str
  elapsed_meeting_sec: float
  camera_on: bool = True
  mic_on: bool = True
  screen_share: bool = False
  face_visible: bool = True
  voice_detected: bool = True
  transcript_available: bool = True
  meeting_tags: List[str] = field(default_factory=list)
