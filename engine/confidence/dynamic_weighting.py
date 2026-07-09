"""
Dynamic Confidence Weighting & Decay/Recovery Module (`engine/confidence/dynamic_weighting.py`).

Enforces intelligent weight adjustments based on real-time signal availability and staleness:
- `Camera Off / Face Lost`: Sets face weight -> 0.0 and scales up voice & conversation weights without penalizing overall confidence.
- `No Speech Yet`: Sets voice weight -> 0.0 and scales up identity, face, and conversation weights.
- `Gradual Staleness Decay`: When signals drop out, confidence decays gradually across time rather than crashing instantaneously.
- `Smooth Recovery`: When lost evidence returns, confidence interpolates smoothly without erratic upward jumps.
"""
from typing import Dict, Set, List, Tuple
from engine.confidence.constants import EvidenceSource, ALL_EVIDENCE_SOURCES
from engine.confidence.config import confidence_config
from engine.confidence.models import NormalizedEvidenceItem
from engine.confidence.weighting import WeightManager
from engine.confidence.utils import calculate_exponential_decay, calculate_smooth_recovery, clamp


class DynamicConfidenceWeighting:
  """Applies dynamic rule adjustments, gradual staleness decay, and recovery interpolation."""

  def __init__(self, weight_manager: WeightManager):
    self.weight_manager = weight_manager

  def evaluate_dynamic_weights_and_decay(
      self,
      normalized_items: Dict[str, NormalizedEvidenceItem],
      current_timestamp: float,
      previous_confidence: float,
      highest_confidence: float = 0.0
  ) -> Tuple[Dict[str, float], Set[str], List[str], Dict[str, NormalizedEvidenceItem], Optional[float]]:
    """Evaluate active domains, apply hardware/staleness rules, and check for decay/recovery.

    Returns:
        tuple: (active_weights, active_sources_set, reasons, adjusted_items, decayed_or_recovered_confidence)
    """
    base_weights = self.weight_manager.get_base_weights()
    modified_weights = dict(base_weights)
    active_sources: Set[str] = set()
    missing_sources: Set[str] = set()
    stale_sources: Set[str] = set()
    reasons: List[str] = []
    adjusted_items: Dict[str, NormalizedEvidenceItem] = dict(normalized_items)

    # 1. Inspect freshness across all known domains
    for src in ALL_EVIDENCE_SOURCES:
      item = adjusted_items.get(src)
      if item is None:
        missing_sources.add(src)
        modified_weights[src] = 0.0
        continue

      elapsed_sec = max(0.0, current_timestamp - item.timestamp)

      if elapsed_sec >= confidence_config.EVIDENCE_MISSING_TIMEOUT_SEC:
        # Timed out completely
        missing_sources.add(src)
        item.is_missing = True
        modified_weights[src] = 0.0
        reasons.append(f"{src.capitalize()} evidence missing for >{int(elapsed_sec)}s -> {src.capitalize()} weight set to 0.0")
      elif elapsed_sec >= confidence_config.EVIDENCE_STALE_TIMEOUT_SEC:
        # Stale but not totally lost
        stale_sources.add(src)
        active_sources.add(src)
        item.is_stale = True
        # Reduce effective weight proportionally to staleness
        decay_factor = clamp(1.0 - ((elapsed_sec - 30.0) / 180.0), 0.20, 1.0)
        modified_weights[src] *= decay_factor
        reasons.append(f"{src.capitalize()} evidence stale ({int(elapsed_sec)}s old) -> weight reduced by {(1.0-decay_factor)*100:.0f}%")
      else:
        # Fresh active evidence
        active_sources.add(src)
        item.is_stale = False
        item.is_missing = False

    # 2. Camera Off / Face Lost Rule
    if EvidenceSource.FACE.value not in active_sources:
      modified_weights[EvidenceSource.FACE.value] = 0.0
      if not any("Camera off" in r or "Face evidence" in r for r in reasons):
        reasons.append("Camera off / face evidence absent -> Face weight set to 0.0")
      # Scale up Voice and Conversation
      if EvidenceSource.VOICE.value in active_sources:
        modified_weights[EvidenceSource.VOICE.value] *= 1.35
      if EvidenceSource.CONVERSATION.value in active_sources:
        modified_weights[EvidenceSource.CONVERSATION.value] *= 1.25

    # 3. No Speech / Voice Absent Rule
    if EvidenceSource.VOICE.value not in active_sources:
      modified_weights[EvidenceSource.VOICE.value] = 0.0
      if not any("No speech" in r or "Voice evidence" in r for r in reasons):
        reasons.append("No speech yet / voice evidence absent -> Voice weight set to 0.0")
      # Scale up Identity, Face, and Conversation
      if EvidenceSource.IDENTITY.value in active_sources:
        modified_weights[EvidenceSource.IDENTITY.value] *= 1.30
      if EvidenceSource.FACE.value in active_sources:
        modified_weights[EvidenceSource.FACE.value] *= 1.25
      if EvidenceSource.CONVERSATION.value in active_sources:
        modified_weights[EvidenceSource.CONVERSATION.value] *= 1.20

    # 4. Low Confidence Guard
    for src in list(active_sources):
      item = adjusted_items.get(src)
      if item and item.upstream_confidence < confidence_config.MIN_EVIDENCE_CONFIDENCE_GATE:
        # Dampen weight of very low confidence upstream signals (`< 0.25`)
        modified_weights[src] *= 0.40
        reasons.append(f"Low upstream confidence ({item.upstream_confidence:.2f}) on {src} -> weight dampened by 60%")

    # 5. Normalize modified weights across active sources
    normalized_weights = self.weight_manager.normalize_active_weights(modified_weights, active_sources)

    # 6. Evaluate Gradual Decay or Recovery override on overall confidence
    override_confidence: Optional[float] = None
    if not active_sources or (len(active_sources) == 1 and EvidenceSource.IDENTITY.value in active_sources):
      # If all dynamic stream signals disappeared (`face`, `voice`, `conversation`), decay gradually!
      override_confidence = calculate_exponential_decay(previous_confidence, confidence_config.EVIDENCE_STALE_TIMEOUT_SEC + 30.0)
      reasons.append(f"All primary dynamic streams absent -> gradual confidence decay applied ({previous_confidence:.2f} -> {override_confidence:.2f})")
    elif len(active_sources) >= 2 and highest_confidence > 0.50 and previous_confidence < highest_confidence - 0.15 and previous_confidence > 0.0:
      # If multiple signals returned cleanly after a drop or decay from an earlier high confidence, recover smoothly
      avg_signal = sum(adjusted_items[s].combined_signal_strength for s in active_sources) / len(active_sources)
      if avg_signal > previous_confidence + 0.05:
        override_confidence = calculate_smooth_recovery(previous_confidence, avg_signal)
        reasons.append(f"Multiple active signals recovered -> smooth confidence recovery applied ({previous_confidence:.2f} -> {override_confidence:.2f})")

    return normalized_weights, active_sources, reasons, adjusted_items, override_confidence
