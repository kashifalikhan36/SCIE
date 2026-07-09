import logging
from typing import Optional, List

from engine.association.schemas import (
    ParticipantIdentity,
    ParticipantIdentityState,
    MetadataMatchEvidence,
    TranscriptMatchEvidence,
    SpeakerMatchEvidence,
    TrackMatchEvidence,
    TimelineMatchEvidence,
)
from engine.association.utils import now_ms

logger = logging.getLogger("SCIE.association_engine.participant_builder")


class ParticipantBuilder:
  """Constructs and refines a unified ParticipantIdentity object given existing state,
  fresh matcher evidences, and calculated confidence scores.

  Does NOT perform AI inference. Only deterministic rule-based construction.
  """

  def build(
      self,
      participant_id: str,
      association_score: float,
      association_confidence: float,
      reasons: List[str],
      track_id: Optional[str] = None,
      speaker_id: Optional[str] = None,
      display_name: Optional[str] = None,
      existing_state: Optional[ParticipantIdentityState] = None,
      metadata_evidence: Optional[MetadataMatchEvidence] = None,
      transcript_evidence: Optional[TranscriptMatchEvidence] = None,
      speaker_evidence: Optional[SpeakerMatchEvidence] = None,
      track_evidence: Optional[TrackMatchEvidence] = None,
      timeline_evidence: Optional[TimelineMatchEvidence] = None,
  ) -> ParticipantIdentity:
    """Creates a ParticipantIdentity object merging existing state with fresh matcher data."""
    # 1. Start with resolved and existing attributes
    display_name = display_name or (existing_state.display_name if existing_state else None)
    email = existing_state.email if existing_state else None
    track_id = track_id or (existing_state.track_id if existing_state else None)
    speaker_id = speaker_id or (existing_state.speaker_id if existing_state else None)

    # 2. Update metadata attributes if high-confidence metadata match arrived
    if metadata_evidence and metadata_evidence.score > 0.0:
      if metadata_evidence.matched_name:
        display_name = metadata_evidence.matched_name
      if metadata_evidence.matched_email:
        email = metadata_evidence.matched_email

    # 3. Update display name from transcript self-introductions if not set by metadata
    if not display_name and transcript_evidence and transcript_evidence.extracted_name:
      display_name = transcript_evidence.extracted_name

    # 4. Update track_id and speaker_id from matcher evidence
    if track_evidence and track_evidence.track_id:
      track_id = track_evidence.track_id
    if speaker_evidence and speaker_evidence.speaker_id:
      speaker_id = speaker_evidence.speaker_id

    # 5. Extract individual scores
    m_score = metadata_evidence.score if metadata_evidence else 0.0
    t_score = transcript_evidence.score if transcript_evidence else 0.0
    s_score = speaker_evidence.score if speaker_evidence else 0.0
    tr_score = track_evidence.score if track_evidence else 0.0
    time_score = timeline_evidence.score if timeline_evidence else 0.0

    identity = ParticipantIdentity(
        participant_id=participant_id,
        display_name=display_name,
        email=email,
        track_id=track_id,
        speaker_id=speaker_id,
        metadata_score=round(m_score, 4),
        transcript_score=round(t_score, 4),
        speaker_score=round(s_score, 4),
        track_score=round(tr_score, 4),
        timeline_score=round(time_score, 4),
        association_score=round(association_score, 4),
        association_confidence=round(association_confidence, 4),
        reasons=reasons,
        timestamp=now_ms()
    )

    logger.debug(
        f"ParticipantBuilder: Built identity {participant_id} (name={display_name}, "
        f"track={track_id}, speaker={speaker_id}, conf={association_confidence:.4f})"
    )
    return identity
