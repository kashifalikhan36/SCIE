import logging
from typing import Optional, Any, Dict, List

from engine.association.schemas import (
    ParticipantIdentity,
    ParticipantIdentityState,
    ParticipantAssociation,
    MeetingMetadata,
    MeetingEvent,
)
from engine.video.schemas import VisualEvidence
from engine.audio.schemas import VoiceEvidence
from engine.transcript.schemas import TranscriptEvidence
from engine.association.metadata_matcher import MetadataMatcher
from engine.association.transcript_matcher import TranscriptMatcher
from engine.association.speaker_matcher import SpeakerMatcher
from engine.association.track_matcher import TrackMatcher
from engine.association.timeline_matcher import TimelineMatcher
from engine.association.confidence import ConfidenceCalculator
from engine.association.participant_builder import ParticipantBuilder
from engine.association.state_manager import AssociationStateManager
from engine.association.association_provider import AssociationProvider
from engine.association.storage import AssociationStorageManager
from engine.association.utils import generate_participant_id, now_ms
from engine.association.logger import measure_latency
from engine.association.config import association_config

logger = logging.getLogger("SCIE.association_engine.pipeline")


class ParticipantAssociationPipeline:
  """Orchestrates the end-to-end multi-modal identity resolution flow.

  Data flow:
  Incoming Event (Visual, Voice, Transcript, Metadata, or DOM Event)
    └─ Resolver       (resolve or allocate participant_id via Redis O(1) indices)
    └─ Matchers       (Metadata, Transcript, Speaker, Track, Timeline)
    └─ Confidence     (synthesize weighted association_score and association_confidence)
    └─ Builder        (construct unified ParticipantIdentity)
    └─ StateManager   (synchronize live ParticipantIdentityState in Azure Cache for Redis)
    └─ Storage        (persist audit history and snapshots to 5 MongoDB collections)
    └─ Provider       (emit canonical ParticipantAssociation output for downstream engines)
  """

  def __init__(self):
    self.metadata_matcher = MetadataMatcher()
    self.transcript_matcher = TranscriptMatcher()
    self.speaker_matcher = SpeakerMatcher()
    self.track_matcher = TrackMatcher()
    self.timeline_matcher = TimelineMatcher()
    self.confidence_calc = ConfidenceCalculator()
    self.builder = ParticipantBuilder()
    self.state_manager = AssociationStateManager()
    self.provider = AssociationProvider()
    self.storage = AssociationStorageManager()

  @measure_latency("association_pipeline.process_event")
  async def process_event(
      self,
      meeting_id: str,
      event_data: Any,
      metadata_context: Optional[MeetingMetadata] = None,
  ) -> Optional[ParticipantAssociation]:
    """Processes any incoming multi-modal evidence signal or DOM event into a ParticipantAssociation."""
    try:
      timestamp = now_ms()
      # Log raw trigger event for auditability
      raw_dict = event_data.model_dump() if hasattr(event_data, "model_dump") else dict(event_data)
      await self.storage.save_event(meeting_id, raw_dict)

      # 1. Resolve or allocate candidate participant_id using O(1) Redis indices
      participant_id, track_id, speaker_id, display_name = await self._resolve_identifiers(
          meeting_id, event_data
      )

      # Record in timeline matcher sliding window
      if isinstance(event_data, MeetingEvent):
        self.timeline_matcher.record_event(
            meeting_id=meeting_id,
            event_type=event_data.event_type,
            timestamp=event_data.timestamp,
            track_id=event_data.track_id,
            speaker_id=event_data.speaker_id,
            display_name=event_data.display_name,
        )
      elif isinstance(event_data, VisualEvidence):
        self.timeline_matcher.record_event(
            meeting_id=meeting_id,
            event_type="visual_frame",
            timestamp=event_data.timestamp,
            track_id=event_data.track_id,
        )
      elif isinstance(event_data, VoiceEvidence):
        self.timeline_matcher.record_event(
            meeting_id=meeting_id,
            event_type="voice_speech",
            timestamp=event_data.timestamp,
            speaker_id=event_data.speaker_id,
        )
      elif isinstance(event_data, TranscriptEvidence):
        self.timeline_matcher.record_event(
            meeting_id=meeting_id,
            event_type="transcript_turn",
            timestamp=event_data.timestamp,
            speaker_id=event_data.speaker_id,
        )

      # 2. Fetch existing state from Redis
      existing_state = await self.state_manager.get_state(meeting_id, participant_id)
      current_name = (
          existing_state.display_name if existing_state and existing_state.display_name
          else display_name
      )
      current_track = existing_state.track_id if existing_state and existing_state.track_id else track_id
      current_speaker = existing_state.speaker_id if existing_state and existing_state.speaker_id else speaker_id

      # 3. Execute individual matchers depending on available context
      meta_ev = None
      if metadata_context:
        meta_ev = self.metadata_matcher.match(
            target_name=current_name,
            target_email=existing_state.email if existing_state else None,
            target_nicknames=None,
            meeting_metadata=metadata_context,
        )

      trans_ev = None
      if isinstance(event_data, TranscriptEvidence):
        trans_ev = await self.transcript_matcher.match(
            target_name=current_name,
            target_speaker_id=current_speaker,
            transcript_evidence=event_data,
        )

      speaker_ev = None
      if isinstance(event_data, VoiceEvidence):
        speaker_ev = self.speaker_matcher.match(
            target_speaker_id=current_speaker,
            voice_evidence=event_data,
        )

      track_ev = None
      if isinstance(event_data, VisualEvidence):
        track_ev = self.track_matcher.match(
            target_track_id=current_track,
            visual_evidence=event_data,
        )

      timeline_ev = self.timeline_matcher.match(
          meeting_id=meeting_id,
          current_timestamp=timestamp,
          target_track_id=current_track,
          target_speaker_id=current_speaker,
          target_display_name=current_name,
      )

      # 4. Synthesize overall association confidence and score
      score, conf, reasons = self.confidence_calc.calculate(
          metadata_evidence=meta_ev,
          transcript_evidence=trans_ev,
          speaker_evidence=speaker_ev,
          track_evidence=track_ev,
          timeline_evidence=timeline_ev,
      )

      # 5. Build unified ParticipantIdentity
      identity = self.builder.build(
          participant_id=participant_id,
          association_score=score,
          association_confidence=conf,
          reasons=reasons,
          track_id=track_id,
          speaker_id=speaker_id,
          display_name=display_name,
          existing_state=existing_state,
          metadata_evidence=meta_ev,
          transcript_evidence=trans_ev,
          speaker_evidence=speaker_ev,
          track_evidence=track_ev,
          timeline_evidence=timeline_ev,
      )

      # 6. Synchronize live state in Redis
      updated_state = await self.state_manager.save_state(
          meeting_id=meeting_id,
          identity=identity,
          existing_state=existing_state,
      )

      # 7. Persist historical records to MongoDB
      await self.storage.save_identity(meeting_id, identity)
      await self.storage.save_timeline_events(meeting_id, participant_id, timeline_ev, timestamp)
      await self.storage.save_confidence_snapshot(
          meeting_id, participant_id, score, conf, reasons, timestamp
      )

      # 8. Emit final canonical ParticipantAssociation and store in association_history
      association = self.provider.provide(meeting_id, updated_state, reasons)
      await self.storage.save_history(meeting_id, association)

      logger.info(
          f"AssociationPipeline: Processed event -> {association.participant_id} "
          f"(name={association.display_name}, track={association.track_id}, "
          f"speaker={association.speaker_id}, conf={association.association_confidence:.4f})"
      )
      return association

    except Exception as exc:
      logger.error(f"AssociationPipeline: Error processing event in meeting {meeting_id}: {exc}")
      return None

  async def _resolve_identifiers(
      self, meeting_id: str, event_data: Any
  ) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Resolves or allocates a participant_id based on incoming track_id or speaker_id."""
    track_id: Optional[str] = None
    speaker_id: Optional[str] = None
    display_name: Optional[str] = None

    if isinstance(event_data, VisualEvidence):
      track_id = event_data.track_id
    elif isinstance(event_data, VoiceEvidence):
      speaker_id = event_data.speaker_id
    elif isinstance(event_data, TranscriptEvidence):
      speaker_id = event_data.speaker_id
    elif isinstance(event_data, MeetingEvent):
      track_id = event_data.track_id
      speaker_id = event_data.speaker_id
      display_name = event_data.display_name

    # Check O(1) Redis index maps first
    if track_id:
      pid = await self.state_manager.lookup_by_track_id(meeting_id, track_id)
      if pid:
        return pid, track_id, speaker_id, display_name

    if speaker_id:
      pid = await self.state_manager.lookup_by_speaker_id(meeting_id, speaker_id)
      if pid:
        return pid, track_id, speaker_id, display_name

    # If new signal without prior mapping, generate a new deterministic participant_id
    new_pid = generate_participant_id()
    logger.info(
        f"AssociationPipeline: Allocated new participant_id {new_pid} for meeting {meeting_id} "
        f"(track={track_id}, speaker={speaker_id})"
    )
    return new_pid, track_id, speaker_id, display_name
