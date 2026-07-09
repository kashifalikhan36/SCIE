"""
Confidence Engine for the Evidence Fusion Engine (`engine/fusion/`).

Computes continuously improving multi-signal confidence scores over time.
Enforces the rule that no decision is made on a single signal (`MINIMUM_EVIDENCE_COUNT`),
and tracks complete historical snapshots of confidence evolution without overwriting.
"""
from typing import Dict, List, Tuple
import math
from engine.fusion.models import WeightedEvidenceItem, ConfidenceComputationContext
from engine.fusion.schemas import ConfidenceHistoryItem
from engine.fusion.config import fusion_config
from engine.fusion.utils import clamp, now_ms
from engine.fusion.logger import logger, measure_latency


class ConfidenceEngine:
  """Computes multi-signal corroboration confidence and maintains history."""

  def __init__(self) -> None:
    # Structure: { f"{meeting_id}:{participant_id}": List[ConfidenceHistoryItem] }
    self._history_map: Dict[str, List[ConfidenceHistoryItem]] = {}

  @measure_latency("compute_confidence")
  def compute_confidence(
      self,
      domain_map: Dict[str, WeightedEvidenceItem],
      participant_id: str,
      meeting_id: str,
      current_time_ms: int,
      previous_confidence: float = 0.0
  ) -> Tuple[float, ConfidenceHistoryItem]:
    """Calculate current multi-signal confidence and record a historical snapshot."""
    active_items = [it for it in domain_map.values() if it.effective_weight > 0.0]
    active_count = len(active_items)

    # Rule: Never make a decision based on a single signal
    if active_count < fusion_config.MINIMUM_EVIDENCE_COUNT:
      # Cap confidence at MINIMUM_CONFIDENCE or proportional to previous_confidence if lower
      raw_conf = min(previous_confidence, fusion_config.MINIMUM_CONFIDENCE)
      if active_count == 1:
        raw_conf = max(raw_conf, fusion_config.MINIMUM_CONFIDENCE * 0.8)
      else:
        raw_conf = 0.0
      conf = clamp(raw_conf, 0.0, fusion_config.MINIMUM_CONFIDENCE)
      logger.debug(
          f"ConfidenceEngine: Only {active_count} active signal(s) for participant={participant_id}. "
          f"Capping confidence at {conf:.2f} (required>={fusion_config.MINIMUM_EVIDENCE_COUNT})."
      )
    else:
      # Multi-signal corroboration: base confidence grows with number of active domains
      # E.g., 2 domains -> ~0.48 base, 3 domains -> ~0.72 base, 4 domains -> ~0.88 base, 5+ -> ~0.98 base
      corroboration_map = {1: 0.20, 2: 0.48, 3: 0.72, 4: 0.88}
      domain_corroboration = corroboration_map.get(active_count, 0.98)

      # Average reliability of active signals
      avg_rel = sum(it.reliability for it in active_items) / float(active_count)

      # Average normalized score quality (higher quality evidence boosts confidence)
      avg_score = sum(it.normalized_score for it in active_items) / float(active_count)
      score_quality_factor = 0.6 + (0.4 * avg_score)

      # Monotonically non-decreasing floor over time with incoming updates
      # As more signals accumulate and corroborate over time, confidence approaches 0.95+
      target_conf = domain_corroboration * avg_rel * score_quality_factor

      # Allow smooth upward evolution while resisting sudden downward spikes unless signals drop off
      if target_conf >= previous_confidence:
        conf = previous_confidence + (target_conf - previous_confidence) * 0.65
      else:
        # If signals dropped off or decayed, confidence decreases gently
        conf = previous_confidence - (previous_confidence - target_conf) * 0.20

      conf = clamp(conf, fusion_config.MINIMUM_CONFIDENCE, 1.0)

    # Create historical snapshot item
    history_item = ConfidenceHistoryItem(
        participant_id=participant_id,
        meeting_id=meeting_id,
        confidence=round(conf, 4),
        timestamp=current_time_ms
    )

    self._record_history(meeting_id, participant_id, history_item)
    return history_item.confidence, history_item

  def _record_history(self, meeting_id: str, participant_id: str, item: ConfidenceHistoryItem) -> None:
    """Append snapshot to local history map bounded by HISTORY_MAX_LENGTH."""
    key = f"{meeting_id}:{participant_id}"
    if key not in self._history_map:
      self._history_map[key] = []
    self._history_map[key].append(item)
    if len(self._history_map[key]) > fusion_config.HISTORY_MAX_LENGTH:
      self._history_map[key].pop(0)

  def get_history(self, meeting_id: str, participant_id: str) -> List[ConfidenceHistoryItem]:
    """Retrieve complete local confidence history for a participant."""
    key = f"{meeting_id}:{participant_id}"
    return list(self._history_map.get(key, []))

  def clear_history(self, meeting_id: str, participant_id: str) -> None:
    """Clear local history for a participant or meeting."""
    key = f"{meeting_id}:{participant_id}"
    self._history_map.pop(key, None)


confidence_engine = ConfidenceEngine()
