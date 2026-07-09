"""
Dynamic Weighting Engine for the Evidence Fusion Engine (`engine/fusion/`).

Adjusts domain weights dynamically depending on signal availability, freshness decay,
and missing evidence rules (e.g., Camera Off sets visual weight to 0 without penalizing score).
"""
from typing import Dict, List
import time
from engine.fusion.schemas import ParticipantState
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.constants import (
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT,
    EvidenceStatus
)
from engine.fusion.config import fusion_config
from engine.fusion.utils import calculate_time_decay, clamp, safe_divide
from engine.fusion.logger import logger, measure_latency


class DynamicWeightingEngine:
  """Calculates adaptive domain weights and freshness multipliers."""

  @measure_latency("compute_dynamic_weights")
  def compute_dynamic_weights(
      self,
      state: ParticipantState,
      current_time_ms: int
  ) -> Dict[str, WeightedEvidenceItem]:
    """Inspect participant evidence slots, determine availability and age, and compute normalized weights."""
    current_sec = current_time_ms / 1000.0
    domain_map: Dict[str, WeightedEvidenceItem] = {}

    # Inspect the standard domains
    slots = [
        (DOMAIN_IDENTITY, state.identity_evidence),
        (DOMAIN_VISUAL, state.visual_evidence),
        (DOMAIN_VOICE, state.voice_evidence),
        (DOMAIN_BEHAVIOR, state.behavior_evidence),
        (DOMAIN_CONVERSATION, state.conversation_evidence),
        (DOMAIN_TRANSCRIPT, state.transcript_evidence),
    ]

    # Also include any extra domains dynamically
    for extra_dom, extra_dict in state.extra_evidence.items():
      slots.append((extra_dom, extra_dict))

    base_weights = dict(fusion_config.DEFAULT_WEIGHTS)

    for domain, slot_dict in slots:
      item = WeightedEvidenceItem(domain=domain)
      if not slot_dict:
        item.status = EvidenceStatus.UNAVAILABLE
        item.effective_weight = 0.0
      else:
        # Check status field
        status_str = slot_dict.get("status", EvidenceStatus.AVAILABLE.value)
        try:
          item.status = EvidenceStatus(status_str)
        except ValueError:
          item.status = EvidenceStatus.AVAILABLE

        if item.status in (EvidenceStatus.UNAVAILABLE, EvidenceStatus.FAILED):
          item.effective_weight = 0.0
        else:
          ts_ms = slot_dict.get("timestamp", current_time_ms)
          age_sec = max(0.0, current_sec - (ts_ms / 1000.0))
          item.age_seconds = age_sec

          # Determine staleness and time decay
          if age_sec > fusion_config.MAX_STALE_DURATION_SEC:
            item.status = EvidenceStatus.STALE
            item.freshness_multiplier = calculate_time_decay(
                age_sec - fusion_config.FRESHNESS_TIMEOUT_SEC,
                half_life_sec=60.0
            )
          elif age_sec > fusion_config.FRESHNESS_TIMEOUT_SEC:
            item.freshness_multiplier = calculate_time_decay(
                age_sec - fusion_config.FRESHNESS_TIMEOUT_SEC,
                half_life_sec=120.0
            )
          else:
            item.freshness_multiplier = 1.0

          # Extract score and reliability
          item.raw_score = float(slot_dict.get("score", 0.0))
          item.reliability = float(slot_dict.get("reliability", 1.0))

          # Initial unnormalized weight is base weight * freshness multiplier
          base_w = base_weights.get(domain, 0.10)
          item.effective_weight = base_w * item.freshness_multiplier

      domain_map[domain] = item

    # Normalize weights across all active domains so sum(weights) == 1.0
    total_weight = sum(it.effective_weight for it in domain_map.values() if it.effective_weight > 0.0)
    if total_weight > 0.0:
      for it in domain_map.values():
        if it.effective_weight > 0.0:
          it.effective_weight = safe_divide(it.effective_weight, total_weight, default=0.0)
    else:
      logger.debug(f"DynamicWeightingEngine: No active evidence weights for participant={state.participant_id}.")

    return domain_map


dynamic_weighting_engine = DynamicWeightingEngine()
