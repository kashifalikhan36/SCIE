"""
Weight Manager Module for the SCIE Confidence Engine (`engine/confidence/weighting.py`).

Maintains configurable domain weights (`identity`, `face`, `voice`, `conversation`,
`behavior`, `transcript`, `emotion`, `gaze`) without hardcoded magic numbers.
Allows runtime weight overrides and pluggable configuration profiles.
"""
from typing import Dict, Set
from engine.confidence.constants import ALL_EVIDENCE_SOURCES
from engine.confidence.config import confidence_config
from engine.confidence.utils import safe_divide, clamp
from engine.confidence.exceptions import ConfidenceWeightError


class WeightManager:
  """Manages configurable base weights and exact normalization across active sources."""

  def __init__(self, initial_weights: Dict[str, float] = None):
    self._base_weights: Dict[str, float] = dict(initial_weights or confidence_config.DEFAULT_WEIGHTS)
    self._ensure_complete_domains()

  def _ensure_complete_domains(self) -> None:
    """Ensure every recognized evidence source is present in the internal weight map."""
    for dom in ALL_EVIDENCE_SOURCES:
      if dom not in self._base_weights:
        self._base_weights[dom] = confidence_config.DEFAULT_WEIGHTS.get(dom, 0.10)

  def get_base_weights(self) -> Dict[str, float]:
    """Return a clean copy of the configured base weights."""
    return dict(self._base_weights)

  def set_base_weight(self, source: str, weight: float) -> None:
    """Dynamically update base weight for a specific domain."""
    src = source.lower().strip()
    if weight < 0.0:
      raise ConfidenceWeightError(f"Weight for {src} cannot be negative ({weight})")
    self._base_weights[src] = float(weight)

  def set_all_base_weights(self, weights: Dict[str, float]) -> None:
    """Overwrite all base weights at once."""
    for k, v in weights.items():
      if v < 0.0:
        raise ConfidenceWeightError(f"Weight for {k} cannot be negative ({v})")
      self._base_weights[k.lower().strip()] = float(v)
    self._ensure_complete_domains()

  def normalize_active_weights(
      self,
      raw_weights: Dict[str, float],
      active_sources: Set[str]
  ) -> Dict[str, float]:
    """Normalize raw weights strictly across `active_sources` so sum == 1.0."""
    total_raw = sum(max(0.0, raw_weights.get(src, 0.0)) for src in active_sources)

    if total_raw <= 1e-12:
      # If raw active weights sum to zero, distribute equally among active sources
      if active_sources:
        eq = safe_divide(1.0, len(active_sources), 0.0)
        return {src: (eq if src in active_sources else 0.0) for src in ALL_EVIDENCE_SOURCES}
      else:
        # If no active sources exist, return zero weights across all
        return {src: 0.0 for src in ALL_EVIDENCE_SOURCES}

    norm_factor = safe_divide(1.0, total_raw, 1.0)
    normalized: Dict[str, float] = {}
    for src in ALL_EVIDENCE_SOURCES:
      if src in active_sources:
        raw_val = max(0.0, float(raw_weights.get(src, 0.0)))
        normalized[src] = clamp(raw_val * norm_factor, 0.0, 1.0)
      else:
        normalized[src] = 0.0

    return normalized
