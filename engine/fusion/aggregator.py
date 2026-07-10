"""
Evidence Aggregator for the Evidence Fusion Engine (`engine/fusion/`).

Responsible for asynchronously receiving, validating, and merging incoming evidence
into a unified ParticipantState. Handles out-of-order delivery and duplicates without
computing confidence or ranking directly.
"""
from typing import Optional, Dict, Any
from engine.fusion.schemas import IncomingEvidence, ParticipantState
from engine.fusion.constants import (
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT,
    EvidenceStatus
)
from engine.fusion.exceptions import DuplicateEvidenceError, EvidenceAggregationError
from engine.fusion.evidence_cache import evidence_cache
from engine.fusion.utils import now_ms
from engine.fusion.logger import logger, measure_latency


class EvidenceAggregator:
  """Aggregates incoming evidence streams into unified ParticipantState objects."""

  @measure_latency("aggregate_evidence")
  async def aggregate_evidence(
      self,
      evidence: IncomingEvidence,
      current_state: Optional[ParticipantState] = None
  ) -> ParticipantState:
    """Validate and merge an incoming evidence item into a ParticipantState.

    If current_state is None, initializes a fresh ParticipantState.
    Handles duplicate and out-of-order evidence cleanly.
    """
    try:
      # 1. Deduplication check
      if evidence_cache.is_duplicate(evidence):
        logger.debug(f"EvidenceAggregator: Skipping duplicate item {evidence.evidence_id}.")
        raise DuplicateEvidenceError(f"Duplicate evidence ID {evidence.evidence_id}")

      # 2. Resolve target participant ID
      pid = evidence.participant_id
      if not pid and current_state:
        pid = current_state.participant_id
      if not pid:
        # Fallback to track_id or speaker_id if available
        pid = evidence.track_id or evidence.speaker_id or f"p_{evidence.meeting_id}_{now_ms()}"

      # 3. Initialize or update state
      if current_state is None:
        state = ParticipantState(
            participant_id=pid,
            meeting_id=evidence.meeting_id,
            track_id=evidence.track_id,
            speaker_id=evidence.speaker_id,
            last_updated=evidence.timestamp
        )
      else:
        state = current_state.model_copy(deep=True)
        # Update identifiers if previously missing
        if not state.track_id and evidence.track_id:
          state.track_id = evidence.track_id
        if not state.speaker_id and evidence.speaker_id:
          state.speaker_id = evidence.speaker_id
        state.last_updated = max(state.last_updated, evidence.timestamp)

      # Extract display name if present in identity metadata or conversation
      if evidence.source_type == DOMAIN_IDENTITY and not state.display_name:
        display_name = evidence.payload.get("raw_participant_name") or evidence.payload.get("display_name")
        if display_name:
          state.display_name = str(display_name)
      elif evidence.source_type == DOMAIN_CONVERSATION and evidence.payload.get("extracted_name"):
        state.display_name = str(evidence.payload.get("extracted_name"))

      # 4. Out-of-order merge logic into specific domain slots
      domain_dict = {
          "evidence_id": evidence.evidence_id,
          "score": evidence.score,
          "reliability": evidence.reliability,
          "timestamp": evidence.timestamp,
          "status": evidence.status.value,
          "payload": evidence.payload
      }

      self._assign_domain_evidence(state, evidence.source_type, domain_dict, evidence.timestamp)

      # Update cache
      evidence_cache.set_evidence_item(state.meeting_id, state.participant_id, evidence)
      logger.debug(
          f"EvidenceAggregator: Aggregated {evidence.source_type} (score={evidence.score:.2f}) "
          f"for participant={state.participant_id}."
      )
      return state

    except DuplicateEvidenceError:
      raise
    except Exception as exc:
      logger.error(f"EvidenceAggregator: Failed to aggregate evidence {evidence.evidence_id}: {exc}", exc_info=True)
      raise EvidenceAggregationError(f"Aggregation failed: {exc}") from exc

  def _assign_domain_evidence(
      self,
      state: ParticipantState,
      domain: str,
      new_item: Dict[str, Any],
      new_timestamp: int
  ) -> None:
    """Assign domain evidence while handling out-of-order timestamp rules."""
    existing_slot: Optional[Dict[str, Any]] = None

    if domain == DOMAIN_IDENTITY:
      existing_slot = state.identity_evidence
    elif domain == DOMAIN_VISUAL:
      existing_slot = state.visual_evidence
    elif domain == DOMAIN_VOICE:
      existing_slot = state.voice_evidence
    elif domain == DOMAIN_BEHAVIOR:
      existing_slot = state.behavior_evidence
    elif domain == DOMAIN_CONVERSATION:
      existing_slot = state.conversation_evidence
    elif domain == DOMAIN_TRANSCRIPT:
      existing_slot = state.transcript_evidence
    else:
      existing_slot = state.extra_evidence.get(domain)

    # Check out-of-order: if an existing item has a newer timestamp, we do not overwrite the primary score,
    # but we can retain historical trace. If the new item is newer or equal, we update the primary slot.
    if existing_slot and existing_slot.get("timestamp", 0) > new_timestamp:
      logger.debug(
          f"EvidenceAggregator: Out-of-order item for domain={domain}. "
          f"Existing timestamp={existing_slot.get('timestamp')} > new={new_timestamp}. Retaining latest."
      )
      return

    if domain == DOMAIN_IDENTITY:
      state.identity_evidence = new_item
    elif domain == DOMAIN_VISUAL:
      state.visual_evidence = new_item
    elif domain == DOMAIN_VOICE:
      state.voice_evidence = new_item
    elif domain == DOMAIN_BEHAVIOR:
      state.behavior_evidence = new_item
    elif domain == DOMAIN_CONVERSATION:
      state.conversation_evidence = new_item
    elif domain == DOMAIN_TRANSCRIPT:
      state.transcript_evidence = new_item
    else:
      state.extra_evidence[domain] = new_item


evidence_aggregator = EvidenceAggregator()
