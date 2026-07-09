"""
Weighting Strategy Selection Module for the Dynamic Weighting Engine.

Selects active base weight profiles depending on meeting context tags, elapsed time,
and hardware toggles (camera_on, mic_on). Supports future pluggable strategies.

(`engine/weighting/strategy.py`)
"""
from typing import Dict, Optional
from engine.weighting.constants import WeightingStrategyType, ALL_DOMAINS
from engine.weighting.config import weighting_config
from engine.weighting.models import StrategyEvaluationContext
from engine.weighting.exceptions import StrategyEvaluationError
from engine.weighting.logger import logger


class StrategySelector:
  """Selects and retrieves base domain weights for the active meeting context."""

  def __init__(self):
    self._registry: Dict[WeightingStrategyType, Dict[str, float]] = {
        WeightingStrategyType.DEFAULT: weighting_config.DEFAULT_STRATEGY_WEIGHTS,
        WeightingStrategyType.INTERVIEW_STARTED: weighting_config.INTERVIEW_STARTED_WEIGHTS,
        WeightingStrategyType.INTERVIEW_IN_PROGRESS: weighting_config.INTERVIEW_IN_PROGRESS_WEIGHTS,
        WeightingStrategyType.CODING_ROUND: weighting_config.CODING_ROUND_WEIGHTS,
        WeightingStrategyType.BEHAVIOR_ROUND: weighting_config.BEHAVIOR_ROUND_WEIGHTS,
        WeightingStrategyType.CAMERA_OFF: weighting_config.CAMERA_OFF_WEIGHTS,
        WeightingStrategyType.VOICE_ONLY: weighting_config.VOICE_ONLY_WEIGHTS,
        WeightingStrategyType.VIDEO_ONLY: weighting_config.VIDEO_ONLY_WEIGHTS,
        WeightingStrategyType.METADATA_ONLY: weighting_config.METADATA_ONLY_WEIGHTS,
    }

  def register_strategy(self, strategy_type: WeightingStrategyType, weights: Dict[str, float]):
    """Register custom or future weighting strategies (e.g. emotion/deepfake profiles)."""
    for dom in ALL_DOMAINS:
      if dom not in weights:
        raise StrategyEvaluationError(f"Registered strategy {strategy_type} missing domain: {dom}")
    self._registry[strategy_type] = weights
    logger.info(f"Registered custom weighting strategy: {strategy_type}")

  def select_strategy(self, context: StrategyEvaluationContext) -> WeightingStrategyType:
    """Determine best strategy enum based on explicit tags and real-time state."""
    tags = [t.upper() for t in context.meeting_tags]

    # Explicit round overrides
    if "CODING_ROUND" in tags or "CODING" in tags:
      return WeightingStrategyType.CODING_ROUND
    if "BEHAVIOR_ROUND" in tags or "BEHAVIORAL" in tags:
      return WeightingStrategyType.BEHAVIOR_ROUND
    if "METADATA_ONLY" in tags:
      return WeightingStrategyType.METADATA_ONLY
    if "VOICE_ONLY" in tags or (context.mic_on and not context.camera_on and not context.face_visible):
      return WeightingStrategyType.VOICE_ONLY
    if "VIDEO_ONLY" in tags or (context.camera_on and not context.mic_on):
      return WeightingStrategyType.VIDEO_ONLY

    # Hardware states
    if not context.camera_on or not context.face_visible:
      return WeightingStrategyType.CAMERA_OFF

    # Elapsed time stages
    if context.elapsed_meeting_sec < 180.0:
      return WeightingStrategyType.INTERVIEW_STARTED
    elif context.elapsed_meeting_sec >= 180.0:
      return WeightingStrategyType.INTERVIEW_IN_PROGRESS

    return WeightingStrategyType.DEFAULT

  def get_base_weights(self, strategy_type: WeightingStrategyType) -> Dict[str, float]:
    """Retrieve base domain weights for a given strategy enum."""
    return self._registry.get(strategy_type, weighting_config.DEFAULT_STRATEGY_WEIGHTS).copy()
