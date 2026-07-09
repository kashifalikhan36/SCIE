"""
Evidence Fusion Pipeline (`engine/fusion/pipeline.py`).

Orchestrates the complete evidence fusion workflow across SCIE:
1. Ingests and deduplicates evidence from any upstream engine (`IncomingEvidence`).
2. Aggregates domain evidence into unified `ParticipantState` objects (`EvidenceAggregator`).
3. Dynamically adjusts domain weights based on signal availability and freshness (`DynamicWeightingEngine`).
4. Normalizes scores and combines with reliability (`EvidenceScorer`).
5. Computes monotonically evolving multi-signal confidence (`ConfidenceEngine`).
6. Ranks all active participants in the meeting (`ParticipantRanker`).
7. Generates structured rule-based explanations (`ExplanationBuilder`).
8. Updates live state in Azure Cache for Redis (`FusionStateManager`).
9. Persists complete audit logs across 7 MongoDB collections (`FusionPersistenceManager`).
"""
from typing import Optional, Dict
from engine.fusion.schemas import IncomingEvidence, ParticipantState, FusionResult
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.aggregator import evidence_aggregator
from engine.fusion.weighting import dynamic_weighting_engine
from engine.fusion.scorer import evidence_scorer
from engine.fusion.confidence import confidence_engine
from engine.fusion.participant_ranker import participant_ranker
from engine.fusion.explanation import explanation_builder
from engine.fusion.state_manager import fusion_state_manager
from engine.fusion.persistence import fusion_persistence_manager
from engine.fusion.exceptions import DuplicateEvidenceError, FusionEngineException
from engine.fusion.utils import now_ms
from engine.fusion.logger import logger, measure_latency


class FusionPipeline:
  """Orchestrates end-to-end multi-signal evidence fusion, confidence computation, and ranking."""

  @measure_latency("pipeline_process_evidence")
  async def process_evidence(self, evidence: IncomingEvidence) -> Optional[FusionResult]:
    """Process an incoming evidence item, update state, compute confidence/ranking, and persist across Redis/MongoDB."""
    meeting_id = evidence.meeting_id
    # Attempt to resolve participant ID from existing state or evidence payload
    target_pid = evidence.participant_id
    if not target_pid and evidence.track_id:
      target_pid = f"track_{evidence.track_id}"
    elif not target_pid and evidence.speaker_id:
      target_pid = f"speaker_{evidence.speaker_id}"
    elif not target_pid:
      target_pid = f"p_{meeting_id}_default"

    try:
      # Ensure meeting initialized in persistence
      await fusion_persistence_manager.save_meeting_info(meeting_id)

      # 1. Retrieve existing live ParticipantState from Redis if available
      current_state = await fusion_state_manager.get_participant_state(meeting_id, target_pid)
      previous_confidence = current_state.confidence if current_state else 0.0

      # 2. Aggregate incoming evidence item into state
      state = await evidence_aggregator.aggregate_evidence(evidence, current_state=current_state)

      # 3. Compute dynamic weights & freshness decay
      current_time = max(state.last_updated, evidence.timestamp) if (evidence.timestamp and evidence.timestamp > 0) else now_ms()
      domain_map = dynamic_weighting_engine.compute_dynamic_weights(state, current_time)

      # 4. Normalize and score domain items
      domain_map = evidence_scorer.normalize_and_score(domain_map)

      # 5. Compute evolving multi-signal confidence
      new_conf, conf_item = confidence_engine.compute_confidence(
          domain_map=domain_map,
          participant_id=state.participant_id,
          meeting_id=meeting_id,
          current_time_ms=current_time,
          previous_confidence=previous_confidence
      )
      state.confidence = new_conf

      # Update reasons on ParticipantState from top scored domain items
      top_reasons = []
      for it in domain_map.values():
        for r in it.reasons:
          if r not in top_reasons and not r.startswith("Note:"):
            top_reasons.append(r)
      state.reasons = top_reasons[:6]

      # 6. Persist participant state & confidence snapshots
      await fusion_state_manager.save_participant_state(state)
      await fusion_persistence_manager.save_participant_state_snapshot(state)
      await fusion_state_manager.save_confidence_history(conf_item)
      await fusion_persistence_manager.save_confidence_item(conf_item)

      # 7. Evaluate complete meeting ranking across all active participants
      all_states = await fusion_state_manager.get_all_participant_states(meeting_id)
      # Ensure current state is accurately reflected
      all_states[state.participant_id] = state

      # Build domain maps for all participants (using cached or current computation)
      all_domain_maps: Dict[str, Dict[str, WeightedEvidenceItem]] = {}
      for pid, pstate in all_states.items():
        if pid == state.participant_id:
          all_domain_maps[pid] = domain_map
        else:
          dmap = dynamic_weighting_engine.compute_dynamic_weights(pstate, current_time)
          all_domain_maps[pid] = evidence_scorer.normalize_and_score(dmap)

      ranking_result = participant_ranker.rank_participants(meeting_id, all_states, all_domain_maps)

      # Persist ranking result
      await fusion_state_manager.save_latest_ranking(ranking_result)
      await fusion_persistence_manager.save_ranking_snapshot(ranking_result)

      # 8. Find target participant score and generate rule-based structured explanation
      target_score = next((s for s in ranking_result.ranking if s.participant_id == state.participant_id), None)
      if target_score:
        explanation = explanation_builder.build_explanation(state, target_score, domain_map)
        await fusion_persistence_manager.save_explanation(explanation)
        await fusion_persistence_manager.save_participant_score_snapshot(target_score, meeting_id)

      # 9. Assemble final FusionResult
      rank_val = target_score.rank if target_score else 1
      final_score_val = target_score.final_score if target_score else 0.0
      breakdown = target_score.evidence_breakdown if target_score else {k: v.normalized_score for k, v in domain_map.items()}
      reasons_val = target_score.reasons if target_score else state.reasons

      result = FusionResult(
          meeting_id=meeting_id,
          participant_id=state.participant_id,
          rank=rank_val,
          confidence=state.confidence,
          final_score=final_score_val,
          reasons=reasons_val,
          evidence_breakdown=breakdown,
          timestamp=current_time
      )

      # Log successful audit event
      await fusion_persistence_manager.save_fusion_event(
          meeting_id=meeting_id,
          participant_id=state.participant_id,
          incoming_evidence=evidence,
          result=result,
          status="SUCCESS"
      )

      logger.info(
          f"FusionPipeline: Processed {evidence.source_type} for participant={state.participant_id}. "
          f"Confidence={state.confidence * 100:.1f}%, Rank={rank_val}."
      )
      return result

    except DuplicateEvidenceError as exc:
      logger.debug(f"FusionPipeline: Duplicate evidence skipped: {exc}")
      await fusion_persistence_manager.save_fusion_event(
          meeting_id=meeting_id,
          participant_id=target_pid,
          incoming_evidence=evidence,
          status="DUPLICATE",
          error_message=str(exc)
      )
      return None
    except Exception as exc:
      logger.error(f"FusionPipeline: Execution failed for {evidence.evidence_id}: {exc}", exc_info=True)
      await fusion_persistence_manager.save_fusion_event(
          meeting_id=meeting_id,
          participant_id=target_pid,
          incoming_evidence=evidence,
          status="ERROR",
          error_message=str(exc)
      )
      raise FusionEngineException(f"Pipeline error processing {evidence.evidence_id}: {exc}") from exc


fusion_pipeline = FusionPipeline()
