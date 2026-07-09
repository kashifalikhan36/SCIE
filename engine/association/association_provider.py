import logging
from typing import Optional, List

from engine.association.schemas import ParticipantAssociation, ParticipantIdentityState
from engine.association.utils import now_ms

logger = logging.getLogger("SCIE.association_engine.association_provider")


class AssociationProvider:
  """Produces the final ParticipantAssociation output object of this engine.

  This object becomes the canonical, unified identity output consumed by
  all downstream engines (Behavior Engine, Conversation Reasoning, Evidence Fusion).
  """

  def provide(
      self,
      meeting_id: str,
      state: ParticipantIdentityState,
      reasons: Optional[List[str]] = None,
  ) -> ParticipantAssociation:
    """Transforms a live ParticipantIdentityState into a ParticipantAssociation."""
    reasons_list = reasons if reasons is not None else []
    if not reasons_list and state.history:
      latest_snapshot = state.history[-1]
      reasons_list = latest_snapshot.get("reasons", ["Identity resolved via multi-modal association signals."])

    association = ParticipantAssociation(
        meeting_id=meeting_id,
        participant_id=state.participant_id,
        display_name=state.display_name,
        email=state.email,
        track_id=state.track_id,
        speaker_id=state.speaker_id,
        association_score=round(state.association_score, 4),
        association_confidence=round(state.association_confidence, 4),
        reasons=reasons_list,
        timestamp=now_ms()
    )

    logger.debug(
        f"AssociationProvider: Emitted ParticipantAssociation for {association.participant_id} "
        f"(name={association.display_name}, conf={association.association_confidence:.4f})"
    )
    return association
