"""
Evidence Normalizer Module for the SCIE Confidence Engine (`engine/confidence/normalizer.py`).

Normalizes heterogeneous upstream score ranges strictly into [0.0, 1.0].
Supports pluggable strategy patterns (`LinearNormalizer`, `SigmoidNormalizer`,
`ZScoreNormalizer`, `MinMaxNormalizer`) with no hardcoded domain assumptions.
"""
import math
from abc import ABC, abstractmethod
from typing import Dict, Type
from engine.confidence.constants import NormalizationStrategyType
from engine.confidence.models import RawEvidenceItem, NormalizedEvidenceItem
from engine.confidence.config import confidence_config
from engine.confidence.utils import clamp
from engine.confidence.exceptions import ConfidenceNormalizationError


class ScoreNormalizationStrategy(ABC):
  """Abstract base class for score normalization routines [0.0 -> 1.0]."""

  @abstractmethod
  def normalize(self, raw_item: RawEvidenceItem) -> NormalizedEvidenceItem:
    """Transform `RawEvidenceItem` into `NormalizedEvidenceItem` with scores in [0.0, 1.0]."""
    pass


class LinearNormalizationStrategy(ScoreNormalizationStrategy):
  """Standard linear normalization assuming scores are typically emitted around [0.0, 1.0] or [0.0, 100.0]."""

  def normalize(self, raw_item: RawEvidenceItem) -> NormalizedEvidenceItem:
    s = raw_item.score
    # Automatically scale percentages down to [0.0, 1.0]
    if s > 1.5 and s <= 100.0:
      norm_s = s / 100.0
    else:
      norm_s = clamp(s, 0.0, 1.0)

    combined = clamp(norm_s * raw_item.confidence, 0.0, 1.0)
    return NormalizedEvidenceItem(
        participant_id=raw_item.participant_id,
        source=raw_item.source,
        normalized_score=norm_s,
        upstream_confidence=raw_item.confidence,
        combined_signal_strength=combined,
        reason=raw_item.reason,
        timestamp=raw_item.timestamp
    )


class SigmoidNormalizationStrategy(ScoreNormalizationStrategy):
  """Sigmoidal normalization useful when unbounded logits or raw similarity scores are emitted."""

  def normalize(self, raw_item: RawEvidenceItem) -> NormalizedEvidenceItem:
    s = raw_item.score
    # Standard logistic sigmoid centered at 0 or scaled appropriately
    try:
      norm_s = 1.0 / (1.0 + math.exp(-clamp(s, -10.0, 10.0)))
    except OverflowError:
      norm_s = 1.0 if s > 0 else 0.0

    combined = clamp(norm_s * raw_item.confidence, 0.0, 1.0)
    return NormalizedEvidenceItem(
        participant_id=raw_item.participant_id,
        source=raw_item.source,
        normalized_score=norm_s,
        upstream_confidence=raw_item.confidence,
        combined_signal_strength=combined,
        reason=f"{raw_item.reason} (sigmoid normalized)",
        timestamp=raw_item.timestamp
    )


class MinMaxNormalizationStrategy(ScoreNormalizationStrategy):
  """Min-Max normalization given known bounds extracted from evidence metadata (`min_val`, `max_val`)."""

  def normalize(self, raw_item: RawEvidenceItem) -> NormalizedEvidenceItem:
    s = raw_item.score
    meta = raw_item.metadata
    min_v = float(meta.get("min_score", 0.0))
    max_v = float(meta.get("max_score", 1.0))

    if max_v <= min_v:
      norm_s = clamp(s, 0.0, 1.0)
    else:
      norm_s = clamp((s - min_v) / (max_v - min_v), 0.0, 1.0)

    combined = clamp(norm_s * raw_item.confidence, 0.0, 1.0)
    return NormalizedEvidenceItem(
        participant_id=raw_item.participant_id,
        source=raw_item.source,
        normalized_score=norm_s,
        upstream_confidence=raw_item.confidence,
        combined_signal_strength=combined,
        reason=f"{raw_item.reason} (minmax normalized)",
        timestamp=raw_item.timestamp
    )


class ZScoreNormalizationStrategy(ScoreNormalizationStrategy):
  """Z-score normalization mapped to standard cumulative distribution approximation."""

  def normalize(self, raw_item: RawEvidenceItem) -> NormalizedEvidenceItem:
    s = raw_item.score
    meta = raw_item.metadata
    mean = float(meta.get("mean", 0.0))
    std = max(1e-6, float(meta.get("std", 1.0)))

    z = (s - mean) / std
    # Approximate error function / CDF mapping onto [0, 1]
    norm_s = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    combined = clamp(norm_s * raw_item.confidence, 0.0, 1.0)
    return NormalizedEvidenceItem(
        participant_id=raw_item.participant_id,
        source=raw_item.source,
        normalized_score=clamp(norm_s, 0.0, 1.0),
        upstream_confidence=raw_item.confidence,
        combined_signal_strength=combined,
        reason=f"{raw_item.reason} (zscore normalized)",
        timestamp=raw_item.timestamp
    )


class EvidenceNormalizer:
  """Central normalization engine managing pluggable strategies."""

  def __init__(self, strategy_type: str = confidence_config.DEFAULT_NORMALIZATION_STRATEGY):
    self._registry: Dict[str, ScoreNormalizationStrategy] = {
        NormalizationStrategyType.LINEAR.value: LinearNormalizationStrategy(),
        NormalizationStrategyType.SIGMOID.value: SigmoidNormalizationStrategy(),
        NormalizationStrategyType.MINMAX.value: MinMaxNormalizationStrategy(),
        NormalizationStrategyType.ZSCORE.value: ZScoreNormalizationStrategy(),
    }
    self.set_strategy(strategy_type)

  def set_strategy(self, strategy_type: str) -> None:
    """Change the active normalization strategy dynamically."""
    st_clean = strategy_type.lower().strip()
    if st_clean not in self._registry:
      raise ConfidenceNormalizationError(f"Unsupported normalization strategy: '{strategy_type}'")
    self.active_strategy = self._registry[st_clean]
    self.active_strategy_name = st_clean

  def register_strategy(self, name: str, strategy: ScoreNormalizationStrategy) -> None:
    """Register custom normalization strategy at runtime."""
    if not isinstance(strategy, ScoreNormalizationStrategy):
      raise ConfidenceNormalizationError("Strategy must inherit from ScoreNormalizationStrategy")
    self._registry[name.lower().strip()] = strategy

  def normalize_evidence(self, raw_item: RawEvidenceItem, strategy_override: str = None) -> NormalizedEvidenceItem:
    """Normalize raw evidence item onto [0.0, 1.0] using active or overridden strategy."""
    strat = self.active_strategy
    if strategy_override:
      st_clean = strategy_override.lower().strip()
      if st_clean in self._registry:
        strat = self._registry[st_clean]

    try:
      return strat.normalize(raw_item)
    except Exception as e:
      raise ConfidenceNormalizationError(f"Error normalizing evidence from {raw_item.source}: {e}", details={"item": raw_item.participant_id})
