"""
engine.association
==================

Production-ready Participant Identity Resolution Engine (Participant Association Engine).

Responsibilities:
- Ingest and unify disconnected signals from Video Engine (track_id), Audio Engine (speaker_id),
  Transcript Engine (self-introductions & addressed cues), and DOM/Meeting Metadata.
- Resolve track and speaker identifiers to unified participant identities via deterministic matchers,
  RapidFuzz string similarity, and temporal co-occurrence logic.
- Maintain live participant state in Azure Cache for Redis and reverse lookup indices for O(1) resolution.
- Persist historical associations across five dedicated MongoDB collections without overwriting history.
- Emit structured ParticipantAssociation objects ready for consumption by downstream Behavior Engine,
  Conversation Reasoning Engine, Evidence Fusion Engine, and Confidence Engine.
"""

from engine.association.workers import (
    ParticipantAssociationWorkerManager,
    enqueue_association_event,
)
from engine.association.pipeline import ParticipantAssociationPipeline
from engine.association.config import association_config
from engine.association.schemas import (
    ParticipantIdentity,
    ParticipantIdentityState,
    ParticipantAssociation,
    MeetingMetadata,
    MeetingEvent,
    MetadataMatchEvidence,
    TranscriptMatchEvidence,
    SpeakerMatchEvidence,
    TrackMatchEvidence,
    TimelineMatchEvidence,
)

__all__ = [
    # Worker management
    "ParticipantAssociationWorkerManager",
    "enqueue_association_event",

    # Pipeline
    "ParticipantAssociationPipeline",

    # Configuration
    "association_config",

    # Schemas
    "ParticipantIdentity",
    "ParticipantIdentityState",
    "ParticipantAssociation",
    "MeetingMetadata",
    "MeetingEvent",
    "MetadataMatchEvidence",
    "TranscriptMatchEvidence",
    "SpeakerMatchEvidence",
    "TrackMatchEvidence",
    "TimelineMatchEvidence",
]
