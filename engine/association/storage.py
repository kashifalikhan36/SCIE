import logging
from typing import Dict, Any, List

from database.mongodb import get_mongo_db
from engine.association.schemas import (
    ParticipantIdentity,
    ParticipantAssociation,
    TimelineMatchEvidence,
)
from engine.association.constants import (
    MONGO_PARTICIPANT_IDENTITY_COL,
    MONGO_ASSOCIATION_HISTORY_COL,
    MONGO_IDENTITY_EVENTS_COL,
    MONGO_PARTICIPANT_TIMELINE_COL,
    MONGO_IDENTITY_CONFIDENCE_COL,
)
from engine.association.exceptions import AssociationStorageError

logger = logging.getLogger("SCIE.association_engine.storage")


class AssociationStorageManager:
  """Handles all MongoDB historical persistence for the Participant Association Engine.

  Maintains immutable audit history and time-series snapshots across five dedicated collections:
  - participant_identity: upserts current resolved profile per participant
  - association_history: append-only log whenever identity or confidence updates
  - identity_events: append-only audit log of incoming association trigger events
  - participant_timeline: structured multi-modal temporal co-occurrence events
  - identity_confidence: time-series snapshots of confidence scores for explainability
  """

  async def save_identity(self, meeting_id: str, identity: ParticipantIdentity) -> None:
    """Upserts the latest resolved ParticipantIdentity document."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = identity.model_dump()
      doc["meeting_id"] = meeting_id
      await db[MONGO_PARTICIPANT_IDENTITY_COL].update_one(
          {"meeting_id": meeting_id, "participant_id": identity.participant_id},
          {"$set": doc},
          upsert=True
      )
      logger.debug(f"Storage: Upserted participant_identity for {identity.participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error saving participant_identity: {exc}")

  async def save_history(self, meeting_id: str, association: ParticipantAssociation) -> None:
    """Appends a new record to association_history (never overwrites history)."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = association.model_dump()
      await db[MONGO_ASSOCIATION_HISTORY_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted association_history for {association.participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error saving association_history: {exc}")

  async def save_event(self, meeting_id: str, event_data: Dict[str, Any]) -> None:
    """Appends a raw trigger event to identity_events for auditability."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {**event_data, "meeting_id": meeting_id}
      await db[MONGO_IDENTITY_EVENTS_COL].insert_one(doc)
      logger.debug("Storage: Inserted identity_event.")
    except Exception as exc:
      logger.error(f"Storage: Error saving identity_event: {exc}")

  async def save_timeline_events(
      self,
      meeting_id: str,
      participant_id: str,
      timeline_evidence: TimelineMatchEvidence,
      timestamp: int,
  ) -> None:
    """Appends structured temporal co-occurrence records to participant_timeline."""
    db = get_mongo_db()
    if db is None or not timeline_evidence.co_occurring_events:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "timestamp": timestamp,
          "score": timeline_evidence.score,
          "confidence": timeline_evidence.confidence,
          "co_occurring_events": timeline_evidence.co_occurring_events,
          "reasons": timeline_evidence.reasons,
      }
      await db[MONGO_PARTICIPANT_TIMELINE_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted participant_timeline record for {participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error saving participant_timeline: {exc}")

  async def save_confidence_snapshot(
      self,
      meeting_id: str,
      participant_id: str,
      association_score: float,
      association_confidence: float,
      reasons: List[str],
      timestamp: int,
  ) -> None:
    """Appends a confidence snapshot to identity_confidence for time-series explainability."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "association_score": association_score,
          "association_confidence": association_confidence,
          "reasons": reasons,
          "timestamp": timestamp,
      }
      await db[MONGO_IDENTITY_CONFIDENCE_COL].insert_one(doc)
      logger.debug(f"Storage: Inserted identity_confidence snapshot for {participant_id}")
    except Exception as exc:
      logger.error(f"Storage: Error saving identity_confidence: {exc}")
