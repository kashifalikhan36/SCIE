"""
Confidence Calculator Module with Modular Strategy Pattern (`engine/confidence/calculator.py`).

Computes final participant confidence using pluggable evaluation algorithms:
- `WeightedAverageStrategy`: Normalizes active weights, combines with normalized signal strength, and applies corroboration scaling.
- `BayesianStrategy`: Updates log-odds likelihood based on independent prior updates.
- `LearnedMetaModelStrategy`: Pluggable hook for future ML-based meta-scorers.

Never tightly coupled.
"""
import math
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple
from engine.confidence.constants import CalculationStrategyType
from engine.confidence.models import ConfidenceCalculationContext
from engine.confidence.config import confidence_config
from engine.confidence.utils import clamp
from engine.confidence.exceptions import ConfidenceCalculationError


class ConfidenceStrategy(ABC):
  """Abstract base class for modular confidence calculation algorithms."""

  @abstractmethod
  def calculate(self, ctx: ConfidenceCalculationContext) -> Tuple[float, List[str]]:
    """Compute overall confidence `[0.0, 1.0]` and return `(confidence, additional_reasons)`."""
    pass


class WeightedAverageStrategy(ConfidenceStrategy):
  """Computes confidence using active domain weights, corroboration curves, and single-source guards."""

  def calculate(self, ctx: ConfidenceCalculationContext) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    active_doms = [d for d, w in ctx.active_weights.items() if w > 0.0 and d in ctx.normalized_items]

    if not active_doms:
      reasons.append("No active evidence domains available -> confidence set to 0.0")
      return 0.0, reasons

    # 1. Compute weighted sum across active domains
    weighted_sum = 0.0
    for dom in active_doms:
      item = ctx.normalized_items[dom]
      w = ctx.active_weights[dom]
      weighted_sum += item.combined_signal_strength * w

    # 2. Apply multi-source corroboration multiplier
    count = len(active_doms)
    if count == 1:
      # Guard: single signal alone should not trigger high confidence
      capped = min(weighted_sum, confidence_config.SINGLE_SOURCE_CONFIDENCE_CAP)
      if capped < weighted_sum:
        reasons.append(f"Single active source ({active_doms[0]}) -> confidence capped at {capped:.2f}")
      final_val = capped
    else:
      # Corroboration scaling (up to 1.15x boost when 4+ independent streams corroborate)
      corroboration_boost = clamp(1.0 + (count - 1) * 0.04, 1.0, 1.15)
      final_val = clamp(weighted_sum * corroboration_boost, 0.0, 1.0)
      if corroboration_boost > 1.0:
        reasons.append(f"Multi-source corroboration ({count} active streams) -> {corroboration_boost:.2f}x multiplier applied")

    return clamp(final_val, 0.0, 1.0), reasons


class BayesianStrategy(ConfidenceStrategy):
  """Computes confidence via Bayesian log-odds updating over prior probabilities."""

  def calculate(self, ctx: ConfidenceCalculationContext) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    active_doms = [d for d, w in ctx.active_weights.items() if w > 0.0 and d in ctx.normalized_items]

    if not active_doms:
      return 0.0, ["No active evidence domains for Bayesian update"]

    # Start with base prior or previous confidence as prior
    prior = clamp(ctx.previous_confidence if ctx.previous_confidence > 0.05 else 0.20, 0.05, 0.95)
    log_odds = math.log(prior / (1.0 - prior))

    for dom in active_doms:
      item = ctx.normalized_items[dom]
      w = ctx.active_weights[dom]
      # Signal above 0.5 increases log-odds; below 0.5 decreases log-odds
      signal = clamp(item.combined_signal_strength, 0.05, 0.95)
      likelihood_ratio = signal / (1.0 - signal)
      # Weight modulates the log-odds update step
      log_odds += math.log(likelihood_ratio) * (w * 2.0)

    # Convert back to probability
    posterior = 1.0 / (1.0 + math.exp(-clamp(log_odds, -10.0, 10.0)))
    reasons.append(f"Bayesian log-odds posterior computed across {len(active_doms)} domain(s)")
    return clamp(posterior, 0.0, 1.0), reasons


class LearnedMetaModelStrategy(ConfidenceStrategy):
  """Pluggable hook for future ML meta-models or trained regressors."""

  def calculate(self, ctx: ConfidenceCalculationContext) -> Tuple[float, List[str]]:
    # Fallback directly to WeightedAverageStrategy if no custom model weights are injected
    reasons = ["LearnedMetaModelStrategy active -> delegating to weighted corroboration baseline"]
    fallback = WeightedAverageStrategy()
    val, extra = fallback.calculate(ctx)
    return val, reasons + extra


class ConfidenceCalculator:
  """Central calculation orchestrator managing calculation strategies."""

  def __init__(self, strategy_type: str = confidence_config.DEFAULT_CALCULATION_STRATEGY):
    self._registry: Dict[str, ConfidenceStrategy] = {
        CalculationStrategyType.WEIGHTED_AVERAGE.value: WeightedAverageStrategy(),
        CalculationStrategyType.BAYESIAN.value: BayesianStrategy(),
        CalculationStrategyType.LEARNED_META_MODEL.value: LearnedMetaModelStrategy(),
    }
    self.set_strategy(strategy_type)

  def set_strategy(self, strategy_type: str) -> None:
    """Change the active calculation strategy dynamically."""
    st_clean = strategy_type.lower().strip()
    if st_clean not in self._registry:
      raise ConfidenceCalculationError(f"Unsupported calculation strategy: '{strategy_type}'")
    self.active_strategy = self._registry[st_clean]
    self.active_strategy_name = st_clean

  def register_strategy(self, name: str, strategy: ConfidenceStrategy) -> None:
    """Register custom calculation algorithm at runtime."""
    if not isinstance(strategy, ConfidenceStrategy):
      raise ConfidenceCalculationError("Strategy must inherit from ConfidenceStrategy")
    self._registry[name.lower().strip()] = strategy

  def calculate_confidence(self, ctx: ConfidenceCalculationContext, strategy_override: str = None) -> Tuple[float, List[str]]:
    """Compute overall confidence `[0.0, 1.0]` for the participant context."""
    strat = self.active_strategy
    if strategy_override:
      st_clean = strategy_override.lower().strip()
      if st_clean in self._registry:
        strat = self._registry[st_clean]

    try:
      val, reasons = strat.calculate(ctx)
      return clamp(val, 0.0, 1.0), reasons
    except Exception as e:
      raise ConfidenceCalculationError(f"Error executing calculation strategy '{self.active_strategy_name}': {e}", details={"participant_id": ctx.participant_id})
