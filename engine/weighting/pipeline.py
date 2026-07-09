"""
Orchestration Pipeline for the Dynamic Weighting Engine.

Fetches latest upstream participant context from Redis, aggregates evidence payloads across
all 7 domains, triggers evaluation via ``DynamicWeightingEngine``, and returns the
consumable ``DynamicWeightProfile``.

(`engine/weighting/pipeline.py`)
"""
from typing import Optional, Dict, Any, List
from engine.weighting.schemas import EvidencePayloads, DynamicWeightProfile, UpstreamParticipantState
from engine.weighting.participant_state import ParticipantStateManager
from engine.weighting.engine import DynamicWeightingEngine
from engine.weighting.logger import logger, measure_latency


class WeightingPipeline:
  """High-level orchestration pipeline for weight profile evaluation."""

  def __init__(self, engine: Optional[DynamicWeightingEngine] = None):
    self.engine = engine or DynamicWeightingEngine()
    self.state_manager = ParticipantStateManager()

  @measure_latency("weighting.process_participant")
  async def process_participant(
      self,
      meeting_id: str,
      participant_id: str,
      payloads: Optional[EvidencePayloads] = None,
      elapsed_meeting_sec: float = 0.0,
      meeting_tags: Optional[List[str]] = None,
      force_recompute: bool = False
  ) -> DynamicWeightProfile:
    """Execute end-to-end dynamic weighting evaluation for a participant."""
    logger.debug(f"Starting weight profile evaluation for participant {participant_id} in meeting {meeting_id}")

    # 1. Fetch latest participant state from Redis/memory
    p_state = await self.state_manager.get_participant_state(meeting_id, participant_id)

    # 2. Use empty payloads if none passed
    ev_payloads = payloads or EvidencePayloads()

    # 3. Trigger core dynamic calculation
    profile = await self.engine.compute_weights(
        meeting_id=meeting_id,
        participant_id=participant_id,
        p_state=p_state,
        payloads=ev_payloads,
        elapsed_meeting_sec=elapsed_meeting_sec,
        meeting_tags=meeting_tags,
        force_recompute=force_recompute
    )

    return profile
