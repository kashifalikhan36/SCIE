"""
Internal Data Models for the SCIE Confidence Engine (`engine/confidence/models.py`).

Provides lightweight dataclasses representing pre-processed evidence items,
normalized computation loops, evaluation contexts, and timeline snapshots.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class RawEvidenceItem:
  """Lightweight internal wrapper around validated incoming evidence."""
  participant_id: str
  source: str
  score: float
  confidence: float
  reason: str
  timestamp: float
  metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedEvidenceItem:
  """Normalized evidence representation strictly inside [0.0, 1.0]."""
  participant_id: str
  source: str
  normalized_score: float
  upstream_confidence: float
  combined_signal_strength: float  # score * upstream_confidence
  reason: str
  timestamp: float
  is_stale: bool = False
  is_missing: bool = False


@dataclass
class ConfidenceCalculationContext:
  """Context passed into modular calculation strategies during each update turn."""
  meeting_id: str
  participant_id: str
  current_timestamp: float
  normalized_items: Dict[str, NormalizedEvidenceItem]
  active_weights: Dict[str, float]
  previous_confidence: float
  previous_timeline: List[Dict[str, Any]] = field(default_factory=list)
  force_recompute: bool = False


@dataclass
class TimelineSnapshot:
  """Immutable historical snapshot representing one evaluation step."""
  timestamp: float
  confidence: float
  active_sources_count: int
  active_breakdown: Dict[str, float]
  trend: str
  reasons: List[str]

  def as_dict(self) -> Dict[str, Any]:
    """Convert snapshot to dictionary for Redis/MongoDB storage."""
    return {
        "timestamp": self.timestamp,
        "confidence": self.confidence,
        "active_sources_count": self.active_sources_count,
        "active_breakdown": dict(self.active_breakdown),
        "trend": self.trend,
        "reasons": list(self.reasons)
    }
