"""
Identity Engine — Public API Surface

Exposes the minimal set of objects needed by external consumers
(Fusion Engine, API routes, WebSocket handlers, tests).
"""

from engine.identity.schemas import (
    MeetingMetadata,
    ParticipantMetadata,
    IdentityEvidence,
    ParticipantIdentityState,
    EmailEvidence,
    FuzzyEvidence,
    SemanticEvidence,
    AliasEvidence,
    MetadataEvidence,
)
from engine.identity.pipeline import IdentityPipeline
from engine.identity.workers import IdentityWorkerManager, enqueue_identity_request
from engine.identity.participant_state import IdentityStateManager
from engine.identity.storage import IdentityStorageManager

__all__ = [
    # Schemas
    "MeetingMetadata",
    "ParticipantMetadata",
    "IdentityEvidence",
    "ParticipantIdentityState",
    "EmailEvidence",
    "FuzzyEvidence",
    "SemanticEvidence",
    "AliasEvidence",
    "MetadataEvidence",
    # Core classes
    "IdentityPipeline",
    "IdentityWorkerManager",
    "IdentityStateManager",
    "IdentityStorageManager",
    # Helpers
    "enqueue_identity_request",
]
