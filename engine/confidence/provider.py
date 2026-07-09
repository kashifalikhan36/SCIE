"""
Confidence Provider Module for the SCIE Confidence Engine (`engine/confidence/provider.py`).

Assembles the unified, structured `ConfidenceResult` object consumed by:
- Future Dashboard (`Overall Confidence`, `Evidence Breakdown`, `Active Weights`, `Trend`, `Last Updated`)
- Explanation Engine
- Candidate Selection Engine

Ensures downstream consumers never need to recalculate or derive confidence state.
"""
from typing import Dict, List
from engine.confidence.schemas import ConfidenceResult, ParticipantConfidence
from engine.confidence.models import NormalizedEvidenceItem
from engine.confidence.utils import clamp


class ConfidenceProvider:
  """Produces unified `ConfidenceResult` objects directly from calculated state."""

  def generate_result(
      self,
      state: ParticipantConfidence,
      active_weights: Dict[str, float],
      normalized_items: Dict[str, NormalizedEvidenceItem],
      reasons: List[str],
      trend: str
  ) -> ConfidenceResult:
    """Create exact `ConfidenceResult` ready for dashboard and downstream engines."""
    # Build exact evidence breakdown of normalized contributions (`normalized_score * weight`)
    breakdown: Dict[str, float] = {}
    for src, item in normalized_items.items():
      if not item.is_missing and not item.is_stale:
        w = active_weights.get(src, 0.0)
        breakdown[src] = clamp(item.combined_signal_strength * w, 0.0, 1.0)
      else:
        breakdown[src] = 0.0

    return ConfidenceResult(
        participant_id=state.participant_id,
        meeting_id=state.meeting_id,
        overall_confidence=clamp(state.current_confidence, 0.0, 1.0),
        evidence_breakdown=breakdown,
        active_weights=dict(active_weights),
        reasons=list(reasons),
        trend=trend,
        timestamp=state.last_updated
    )
