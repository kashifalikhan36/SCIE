"""
Core Dynamic Weighting Engine Entrypoint.

Unites evidence validation, quality evaluation, strategy selection, dynamic rules,
weight normalization, calculation caching, and Redis/MongoDB persistence.

(`engine/weighting/engine.py`)
"""
from typing import Dict, Optional
from engine.weighting.constants import (
    ALL_DOMAINS,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
from engine.weighting.schemas import UpstreamParticipantState, EvidencePayloads, DynamicWeightProfile, QualityScores
from engine.weighting.models import StrategyEvaluationContext
from engine.weighting.evidence_validator import EvidenceValidator
from engine.weighting.quality import QualityEvaluator
from engine.weighting.strategy import StrategySelector
from engine.weighting.rules import DynamicRuleEngine
from engine.weighting.scorer import WeightScorerAndNormalizer
from engine.weighting.weight_manager import WeightManager
from engine.weighting.storage import WeightingStorageManager
from engine.weighting.logger import logger, measure_latency


class DynamicWeightingEngine:
  """Production-Ready Dynamic Weighting Engine.

  Computes optimal contribution weights across all 7 evidence sources without calling
  GPT or performing final candidate identification.
  """

  def __init__(self):
    self.validator = EvidenceValidator()
    self.quality_evaluator = QualityEvaluator()
    self.strategy_selector = StrategySelector()
    self.rule_engine = DynamicRuleEngine()
    self.scorer = WeightScorerAndNormalizer()
    self.manager = WeightManager()
    self.storage = WeightingStorageManager()

  @measure_latency("weighting.compute_weights")
  async def compute_weights(
      self,
      meeting_id: str,
      participant_id: str,
      p_state: UpstreamParticipantState,
      payloads: EvidencePayloads,
      elapsed_meeting_sec: float = 0.0,
      meeting_tags: Optional[list] = None,
      force_recompute: bool = False
  ) -> DynamicWeightProfile:
    """Evaluate evidence availability and quality to compute normalized dynamic weights."""
    tags = meeting_tags or []

    # 1. Validate domain availability
    availabilities = self.validator.evaluate_availability(payloads, p_state)

    # 2. Evaluate normalized quality scores [0.0, 1.0]
    quality_scores = self.quality_evaluator.evaluate_quality(payloads, availabilities, p_state)

    # 3. Select active weighting strategy profile
    context = StrategyEvaluationContext(
        meeting_id=meeting_id,
        participant_id=participant_id,
        elapsed_meeting_sec=elapsed_meeting_sec,
        camera_on=p_state.camera_on,
        mic_on=p_state.mic_on,
        screen_share=p_state.screen_share,
        face_visible=p_state.face_visible,
        voice_detected=p_state.voice_detected,
        transcript_available=p_state.transcript_available,
        meeting_tags=tags
    )
    strategy_type = self.strategy_selector.select_strategy(context)

    # Check if calculation can be skipped via cache
    if not self.manager.should_recompute(meeting_id, participant_id, p_state, quality_scores, strategy_type, force_recompute):
      cached = self.manager.get_cached_profile(meeting_id, participant_id)
      if cached:
        logger.debug(f"Retrieved cached dynamic weight profile for {participant_id}")
        return cached

    # Check previous strategy for strategy change audit logging
    old_state = await self.storage.get_latest_state(meeting_id, participant_id)
    previous_strategy = old_state.strategy if old_state else None

    # 4. Retrieve base strategy weights
    base_weights = self.strategy_selector.get_base_weights(strategy_type)

    # 5. Apply dynamic context and quality-driven rules
    modified_weights, reasons = self.rule_engine.apply_rules(
        base_weights=base_weights,
        availabilities=availabilities,
        quality_scores=quality_scores,
        context=context
    )

    # 6. Normalize weights to 1.0 and calculate normalization factor
    normalized_weights, norm_factor, final_reasons = self.scorer.normalize_weights(
        raw_weights=modified_weights,
        reasons=reasons,
        availabilities=availabilities
    )

    # 7. Construct final DynamicWeightProfile
    overall_quality = quality_scores.get_overall_quality()
    profile = DynamicWeightProfile(
        participant_id=participant_id,
        meeting_id=meeting_id,
        visual_weight=normalized_weights[DOMAIN_VISUAL],
        voice_weight=normalized_weights[DOMAIN_VOICE],
        transcript_weight=normalized_weights[DOMAIN_TRANSCRIPT],
        conversation_weight=normalized_weights[DOMAIN_CONVERSATION],
        behavior_weight=normalized_weights[DOMAIN_BEHAVIOR],
        identity_weight=normalized_weights[DOMAIN_IDENTITY],
        metadata_weight=normalized_weights[DOMAIN_METADATA],
        normalization_factor=norm_factor,
        overall_quality=overall_quality,
        strategy_used=strategy_type,
        reasoning=final_reasons
    )

    # 8. Update cache and persist to Redis/MongoDB
    self.manager.update_cache(profile, p_state, quality_scores)
    await self.storage.save_profile(profile, quality_scores, previous_strategy)

    return profile
