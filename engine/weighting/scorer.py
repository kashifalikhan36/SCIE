"""
Weight Normalization & Scoring Module for the Dynamic Weighting Engine.

Normalizes raw modified weights so the sum across all active domains equals 1.0.
Unavailable evidence contributes 0.0 weight.

(`engine/weighting/scorer.py`)
"""
from typing import Dict, List, Tuple
from engine.weighting.constants import (
    ALL_DOMAINS,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
from engine.weighting.config import weighting_config
from engine.weighting.utils import safe_divide, clamp
from engine.weighting.exceptions import WeightNormalizationError


class WeightScorerAndNormalizer:
  """Normalizes weights exactly to 1.0 across active domains and computes normalization factor."""

  def normalize_weights(
      self,
      raw_weights: Dict[str, float],
      reasons: List[str]
  ) -> Tuple[Dict[str, float], float, List[str]]:
    """Normalize domain weights to 1.0 and calculate the normalization factor.

    Returns:
        tuple: (normalized_weights, normalization_factor, formatted_reasons)
    """
    total_raw = sum(max(0.0, float(raw_weights.get(dom, 0.0))) for dom in ALL_DOMAINS)

    if total_raw <= 1e-12:
      # Fallback when all domains are unavailable or 0
      fallback_weights = weighting_config.DEFAULT_STRATEGY_WEIGHTS.copy()
      fallback_total = sum(fallback_weights.values())
      normalized = {dom: safe_divide(fallback_weights.get(dom, 0.0), fallback_total, 0.0) for dom in ALL_DOMAINS}
      reasons_out = list(reasons) + ["All primary domains zero/unavailable -> fallback to normalized DEFAULT strategy weights"]
      return normalized, 1.0, reasons_out

    norm_factor = safe_divide(1.0, total_raw, 1.0)
    normalized = {}
    for dom in ALL_DOMAINS:
      raw_val = max(0.0, float(raw_weights.get(dom, 0.0)))
      normalized[dom] = clamp(raw_val * norm_factor, 0.0, 1.0)

    # Ensure exact precision rounding up to 1.0
    actual_sum = sum(normalized.values())
    if abs(actual_sum - 1.0) > 1e-6 and actual_sum > 0:
      correction = safe_divide(1.0, actual_sum, 1.0)
      for dom in ALL_DOMAINS:
        normalized[dom] = clamp(normalized[dom] * correction, 0.0, 1.0)

    return normalized, norm_factor, reasons
