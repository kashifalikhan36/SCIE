import logging
from typing import Any, Dict, List

from database.mongodb import get_mongo_db
from engine.identity.schemas import IdentityEvidence
from engine.identity.constants import (
    MONGO_IDENTITY_EVIDENCE_COL,
    MONGO_IDENTITY_MATCHES_COL,
    MONGO_PARTICIPANT_IDENTITY_COL,
    MONGO_IDENTITY_EVENTS_COL,
)
from engine.identity.exceptions import IdentityStorageError

logger = logging.getLogger("SCIE.identity_engine.storage")


class IdentityStorageManager:
  """Handles all MongoDB historical persistence for the Identity Engine.

  Collections:
  - ``identity_evidence``: Append-only log of every IdentityEvidence emitted.
  - ``identity_matches``: Records of high-confidence name/email matches.
  - ``identity_participant_profiles``: Upserted current identity profile per participant.
  - ``identity_events``: Raw trigger event audit trail.

  All writes are timestamped. History is never overwritten.
  """

  async def save_evidence(self, evidence: IdentityEvidence) -> None:
    """Appends a complete IdentityEvidence record to the evidence collection.

    This is the primary write operation — called after every pipeline run.

    Args:
        evidence: The IdentityEvidence to persist.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = evidence.model_dump()
      await db[MONGO_IDENTITY_EVIDENCE_COL].insert_one(doc)
      logger.debug(
          f"Storage: Inserted identity_evidence {evidence.evidence_id} "
          f"for participant={evidence.participant_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Error inserting identity_evidence: {exc}")

  async def save_match(
      self,
      meeting_id: str,
      participant_id: str,
      matched_name: str,
      matched_email: str | None,
      score: float,
      confidence: float,
      reasons: List[str],
      timestamp: int,
  ) -> None:
    """Appends a high-confidence match record to identity_matches.

    Args:
        meeting_id: Meeting identifier.
        participant_id: Participant identifier.
        matched_name: Best-matched candidate name variant.
        matched_email: Matched email (if any).
        score: Overall identity score.
        confidence: Overall confidence.
        reasons: Aggregated reasons.
        timestamp: Epoch milliseconds.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "matched_name": matched_name,
          "matched_email": matched_email,
          "score": score,
          "confidence": confidence,
          "reasons": reasons,
          "timestamp": timestamp,
      }
      await db[MONGO_IDENTITY_MATCHES_COL].insert_one(doc)
      logger.debug(
          f"Storage: Inserted identity_match for participant={participant_id} "
          f"(score={score:.4f})"
      )
    except Exception as exc:
      logger.error(f"Storage: Error inserting identity_match: {exc}")

  async def upsert_profile(self, evidence: IdentityEvidence) -> None:
    """Upserts the current identity profile for a participant.

    This keeps the latest resolved identity profile queryable in O(1) time.
    History is preserved in identity_evidence (never overwritten here).

    Args:
        evidence: The IdentityEvidence to upsert as the current profile.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      profile = {
          "meeting_id": evidence.meeting_id,
          "participant_id": evidence.participant_id,
          "display_name": evidence.raw_display_name,
          "normalized_name": evidence.normalized_participant_name,
          "candidate_name": evidence.raw_candidate_name,
          "email": evidence.participant_email,
          "identity_score": evidence.overall_identity_score,
          "confidence": evidence.confidence,
          "email_score": evidence.email_score,
          "rapidfuzz_score": evidence.rapidfuzz_score,
          "semantic_score": evidence.semantic_score,
          "alias_score": evidence.alias_score,
          "metadata_score": evidence.metadata_score,
          "matched_alias": evidence.matched_alias,
          "matched_email": evidence.matched_email,
          "matched_fields": evidence.matched_fields,
          "last_updated": evidence.timestamp,
      }
      await db[MONGO_PARTICIPANT_IDENTITY_COL].update_one(
          {"meeting_id": evidence.meeting_id, "participant_id": evidence.participant_id},
          {"$set": profile},
          upsert=True
      )
      logger.debug(
          f"Storage: Upserted identity_participant_profile for {evidence.participant_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Error upserting identity_participant_profile: {exc}")

  async def save_event(
      self,
      meeting_id: str,
      participant_id: str,
      event_type: str,
      payload: Dict[str, Any],
      timestamp: int,
  ) -> None:
    """Appends a raw trigger event to identity_events for auditability.

    Args:
        meeting_id: Meeting identifier.
        participant_id: Participant identifier.
        event_type: Descriptive event type (e.g. ``"identity_processed"``).
        payload: Raw event payload dictionary.
        timestamp: Epoch milliseconds.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = {
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "event_type": event_type,
          "timestamp": timestamp,
          **payload,
      }
      await db[MONGO_IDENTITY_EVENTS_COL].insert_one(doc)
      logger.debug(
          f"Storage: Inserted identity_event '{event_type}' for participant={participant_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Error inserting identity_event: {exc}")
