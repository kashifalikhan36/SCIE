"""
Participant State Manager for the SCIE Confidence Engine (`engine/confidence/participant_state.py`).

Tracks and updates `ParticipantConfidence` (`current_confidence`, `previous_confidence`,
`highest_confidence`, `lowest_confidence`, `confidence_history`, `last_updated`,
`active_evidence`, `missing_evidence`) across time and syncs with `ConfidenceStorageManager`.
"""
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from engine.confidence.schemas import ParticipantConfidence, ConfidenceEvent
from engine.confidence.models import NormalizedEvidenceItem
from engine.confidence.storage import ConfidenceStorageManager
from engine.confidence.timeline import ConfidenceTimelineManager
from engine.confidence.logger import logger, measure_latency
from engine.confidence.utils import clamp, generate_event_id


class ConfidenceStateManager:
  """Manages rolling state for every participant and coordinates persistence."""

  def __init__(self, storage_manager: Optional[ConfidenceStorageManager] = None):
    self.storage = storage_manager or ConfidenceStorageManager()
    self.timeline_manager = ConfidenceTimelineManager()
    self._lock = asyncio.Lock()

  @measure_latency
  async def get_or_create_state(self, meeting_id: str, participant_id: str) -> ParticipantConfidence:
    """Get existing participant state from cache/memory or initialize baseline state atomically."""
    async with self._lock:
      cached = await self.storage.get_participant_state(meeting_id, participant_id)
      if cached:
        return cached

      new_state = ParticipantConfidence(
          participant_id=participant_id,
          meeting_id=meeting_id,
          current_confidence=0.0,
          previous_confidence=0.0,
          highest_confidence=0.0,
          lowest_confidence=1.0,
          confidence_history=[],
          last_updated=0.0,
          active_evidence={},
          missing_evidence=[]
      )
      self.storage._memory_state[f"{meeting_id}:{participant_id}"] = new_state
      return new_state

  @measure_latency
  async def update_participant_state(
      self,
      state: ParticipantConfidence,
      new_confidence: float,
      active_breakdown: Dict[str, float],
      missing_sources: List[str],
      active_weights: Dict[str, float],
      reasons: List[str],
      current_timestamp: float
  ) -> Tuple[ParticipantConfidence, str, List[ConfidenceEvent]]:
    """Update rolling state, append checkpoints to timeline, generate audit events, and persist."""
    # 1. Capture old bounds and generate shift events
    old_val = state.current_confidence
    events: List[ConfidenceEvent] = []

    if abs(new_confidence - old_val) >= 0.10:
      ev_type = "DECAY_TRIGGERED" if new_confidence < old_val else "RECOVERY_OR_BOOST"
      events.append(ConfidenceEvent(
          event_id=generate_event_id(),
          meeting_id=state.meeting_id,
          participant_id=state.participant_id,
          event_type=ev_type,
          old_confidence=old_val,
          new_confidence=new_confidence,
          reasons=list(reasons),
          timestamp=current_timestamp
      ))

    # 2. Append or update timeline
    updated_hist, trend, _ = self.timeline_manager.append_or_update_timeline(
        existing_history=state.confidence_history,
        current_timestamp=current_timestamp,
        current_confidence=new_confidence,
        active_breakdown=active_breakdown,
        reasons=reasons
    )

    # 3. Construct updated state object
    updated_state = ParticipantConfidence(
        participant_id=state.participant_id,
        meeting_id=state.meeting_id,
        current_confidence=clamp(new_confidence, 0.0, 1.0),
        previous_confidence=old_val,
        highest_confidence=max(state.highest_confidence, new_confidence),
        lowest_confidence=min(state.lowest_confidence, new_confidence),
        confidence_history=updated_hist,
        last_updated=current_timestamp,
        active_evidence=dict(active_breakdown),
        missing_evidence=list(missing_sources)
    )

    # 4. Persist asynchronously to Redis and MongoDB
    await self.storage.save_participant_state(updated_state, active_weights, events)
    return updated_state, trend, events
