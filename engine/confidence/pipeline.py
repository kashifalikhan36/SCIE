"""
Confidence Pipeline Module (`engine/confidence/pipeline.py`).

Orchestrates the complete end-to-end evaluation flow:
1. Ingest raw `Evidence` across any upstream engine (`Identity, Video, Audio, Transcript, Behavior, Conversation`).
2. Validate input boundaries (`validator.py`).
3. Normalize scores onto [0.0, 1.0] via pluggable strategies (`normalizer.py`).
4. Apply dynamic rules, Camera Off shifts, gradual staleness decay, and recovery (`dynamic_weighting.py`).
5. Compute participant confidence via modular calculation algorithms (`calculator.py`).
6. Update rolling state (`ParticipantConfidence`), timeline history, and persist across Redis/MongoDB (`participant_state.py`).
7. Return unified `ConfidenceResult` (`provider.py`) ready for dashboard and downstream engines.
"""
from typing import Dict, List, Optional, Any, Union
from engine.confidence.schemas import Evidence, ConfidenceResult
from engine.confidence.models import RawEvidenceItem, NormalizedEvidenceItem, ConfidenceCalculationContext
from engine.confidence.validator import EvidenceValidator
from engine.confidence.normalizer import EvidenceNormalizer
from engine.confidence.weighting import WeightManager
from engine.confidence.dynamic_weighting import DynamicConfidenceWeighting
from engine.confidence.calculator import ConfidenceCalculator
from engine.confidence.participant_state import ConfidenceStateManager
from engine.confidence.provider import ConfidenceProvider
from engine.confidence.logger import logger, measure_latency
from engine.confidence.utils import current_timestamp_sec, clamp
from engine.confidence.exceptions import ConfidenceValidationError


class ConfidencePipeline:
  """Central async orchestration pipeline for the SCIE Confidence Engine."""

  def __init__(
      self,
      validator: Optional[EvidenceValidator] = None,
      normalizer: Optional[EvidenceNormalizer] = None,
      weight_manager: Optional[WeightManager] = None,
      calculator: Optional[ConfidenceCalculator] = None,
      state_manager: Optional[ConfidenceStateManager] = None,
      provider: Optional[ConfidenceProvider] = None
  ):
    self.validator = validator or EvidenceValidator()
    self.normalizer = normalizer or EvidenceNormalizer()
    self.weight_manager = weight_manager or WeightManager()
    self.dynamic_weighting = DynamicConfidenceWeighting(self.weight_manager)
    self.calculator = calculator or ConfidenceCalculator()
    self.state_manager = state_manager or ConfidenceStateManager()
    self.provider = provider or ConfidenceProvider()

    # In-memory buffer of latest normalized items per participant (`{meeting_id}:{participant_id}` -> `{source: item}`)
    self._participant_evidence_buffer: Dict[str, Dict[str, NormalizedEvidenceItem]] = {}

  @measure_latency
  async def process_evidence(
      self,
      meeting_id: str,
      raw_evidence: Union[Evidence, Dict[str, Any]],
      calculation_strategy: Optional[str] = None
  ) -> Optional[ConfidenceResult]:
    """Ingest, validate, normalize, and evaluate confidence state for a participant upon evidence arrival."""
    # 1. Validate raw evidence
    valid_item = self.validator.validate_and_parse(raw_evidence)
    if not valid_item:
      logger.warning(f"Rejected invalid or malformed evidence in meeting {meeting_id}")
      return None

    # 2. Normalize onto [0.0, 1.0]
    norm_item = self.normalizer.normalize_evidence(valid_item)

    # 3. Buffer normalized evidence in memory for multi-source corroboration
    buf_key = f"{meeting_id}:{norm_item.participant_id}"
    if buf_key not in self._participant_evidence_buffer:
      self._participant_evidence_buffer[buf_key] = {}
    self._participant_evidence_buffer[buf_key][norm_item.source] = norm_item

    # 4. Trigger participant evaluation
    return await self.evaluate_participant(
        meeting_id=meeting_id,
        participant_id=norm_item.participant_id,
        current_timestamp=norm_item.timestamp,
        calculation_strategy=calculation_strategy
    )

  @measure_latency
  async def evaluate_participant(
      self,
      meeting_id: str,
      participant_id: str,
      current_timestamp: Optional[float] = None,
      calculation_strategy: Optional[str] = None
  ) -> ConfidenceResult:
    """Evaluate or re-evaluate latest confidence state for a participant across all known streams."""
    ts = current_timestamp if current_timestamp and current_timestamp > 0 else current_timestamp_sec()
    buf_key = f"{meeting_id}:{participant_id}"
    normalized_map = self._participant_evidence_buffer.get(buf_key, {})

    # 1. Fetch current rolling state from Redis/memory
    state = await self.state_manager.get_or_create_state(meeting_id, participant_id)

    # 2. Evaluate dynamic weights, Camera Off checks, staleness, and decay/recovery
    active_weights, active_sources, dynamic_reasons, adjusted_items, override_conf = (
        self.dynamic_weighting.evaluate_dynamic_weights_and_decay(
            normalized_items=normalized_map,
            current_timestamp=ts,
            previous_confidence=state.current_confidence,
            highest_confidence=state.highest_confidence
        )
    )

    # Update buffer with adjusted items (`is_missing` / `is_stale` tags)
    self._participant_evidence_buffer[buf_key] = adjusted_items

    # 3. Compute overall confidence via calculation strategy
    ctx = ConfidenceCalculationContext(
        meeting_id=meeting_id,
        participant_id=participant_id,
        current_timestamp=ts,
        normalized_items=adjusted_items,
        active_weights=active_weights,
        previous_confidence=state.current_confidence,
        previous_timeline=state.confidence_history
    )

    if override_conf is not None:
      # If gradual decay or recovery override applies, use it directly
      final_val = clamp(override_conf, 0.0, 1.0)
      reasons = dynamic_reasons
    else:
      val, calc_reasons = self.calculator.calculate_confidence(ctx, strategy_override=calculation_strategy)
      final_val = clamp(val, 0.0, 1.0)
      reasons = dynamic_reasons + calc_reasons

    # 4. Calculate active breakdown (`combined_signal * weight`) across available domains
    active_breakdown: Dict[str, float] = {}
    missing_sources: List[str] = []
    for src, item in adjusted_items.items():
      if src in active_sources and not item.is_missing and not item.is_stale:
        w = active_weights.get(src, 0.0)
        active_breakdown[src] = clamp(item.combined_signal_strength * w, 0.0, 1.0)
      else:
        missing_sources.append(src)

    # 5. Update state, timeline history, and persist to Redis + MongoDB
    updated_state, trend, _ = await self.state_manager.update_participant_state(
        state=state,
        new_confidence=final_val,
        active_breakdown=active_breakdown,
        missing_sources=missing_sources,
        active_weights=active_weights,
        reasons=reasons,
        current_timestamp=ts
    )

    # 6. Emit unified ConfidenceResult object
    return self.provider.generate_result(
        state=updated_state,
        active_weights=active_weights,
        normalized_items=adjusted_items,
        reasons=reasons,
        trend=trend
    )
