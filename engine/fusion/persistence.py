"""
MongoDB Persistence Manager for the Evidence Fusion Engine (`engine/fusion/`).

Persists structured fusion data across 7 distinct collections:
- `meetings`: Meeting metadata and fusion initialization timestamps.
- `participant_states`: Historical snapshots of aggregated ParticipantState objects.
- `participant_scores`: Historical snapshots of evaluated ParticipantScore objects.
- `confidence_history`: Chronological audit log of multi-signal confidence evolution.
- `fusion_events`: Audit log of incoming evidence processing cycles (`FE_...`).
- `ranking_history`: Chronological snapshots of complete meeting RankingResult objects.
- `explanations`: Rule-based structured Explanation objects (`EX_...`).

All insertions are non-overwriting append-only records to support complete auditable history.
"""
from typing import List, Dict, Any, Optional
from database.mongodb import get_mongo_db
from engine.fusion.constants import (
    MONGO_MEETINGS_COL,
    MONGO_PARTICIPANT_STATES_COL,
    MONGO_PARTICIPANT_SCORES_COL,
    MONGO_CONFIDENCE_HISTORY_COL,
    MONGO_FUSION_EVENTS_COL,
    MONGO_RANKING_HISTORY_COL,
    MONGO_EXPLANATIONS_COL,
)
from engine.fusion.schemas import (
    ParticipantState,
    ParticipantScore,
    RankingResult,
    Explanation,
    ConfidenceHistoryItem,
    FusionResult,
    IncomingEvidence
)
from engine.fusion.exceptions import FusionStorageError
from engine.fusion.utils import now_ms, generate_fusion_event_id
from engine.fusion.logger import logger, measure_latency


class FusionPersistenceManager:
  """Async MongoDB manager for Evidence Fusion Engine audit persistence."""

  @measure_latency("persist_meeting_event")
  async def save_meeting_info(self, meeting_id: str, extra_data: Optional[Dict[str, Any]] = None) -> None:
    """Persist or update meeting metadata in `meetings` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      doc = {
          "meeting_id": meeting_id,
          "last_fusion_activity": now_ms(),
          "extra_data": extra_data or {}
      }
      await db[MONGO_MEETINGS_COL].update_one(
          {"meeting_id": meeting_id},
          {"$set": doc, "$setOnInsert": {"created_at": now_ms()}},
          upsert=True
      )
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save meeting info: {exc}")
      raise FusionStorageError(f"Failed to save meeting info: {exc}") from exc

  @measure_latency("persist_participant_state")
  async def save_participant_state_snapshot(self, state: ParticipantState) -> None:
    """Append a historical snapshot into `participant_states` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      doc = state.model_dump()
      doc["snapshot_timestamp"] = now_ms()
      await db[MONGO_PARTICIPANT_STATES_COL].insert_one(doc)
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save participant state snapshot: {exc}")
      raise FusionStorageError(f"Failed to save participant state snapshot: {exc}") from exc

  @measure_latency("persist_participant_score")
  async def save_participant_score_snapshot(self, score: ParticipantScore, meeting_id: str) -> None:
    """Append evaluated score object into `participant_scores` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      doc = score.model_dump()
      doc["meeting_id"] = meeting_id
      doc["snapshot_timestamp"] = now_ms()
      await db[MONGO_PARTICIPANT_SCORES_COL].insert_one(doc)
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save participant score snapshot: {exc}")
      raise FusionStorageError(f"Failed to save participant score snapshot: {exc}") from exc

  @measure_latency("persist_confidence_history")
  async def save_confidence_item(self, item: ConfidenceHistoryItem) -> None:
    """Append historical confidence record into `confidence_history` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      await db[MONGO_CONFIDENCE_HISTORY_COL].insert_one(item.model_dump())
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save confidence history item: {exc}")
      raise FusionStorageError(f"Failed to save confidence history item: {exc}") from exc

  @measure_latency("persist_fusion_event")
  async def save_fusion_event(
      self,
      meeting_id: str,
      participant_id: str,
      incoming_evidence: IncomingEvidence,
      result: Optional[FusionResult] = None,
      status: str = "SUCCESS",
      error_message: Optional[str] = None
  ) -> str:
    """Log an audit event record into `fusion_events` collection."""
    try:
      db = get_mongo_db()
      event_id = generate_fusion_event_id()
      if db is None:
        return event_id
      doc = {
          "event_id": event_id,
          "meeting_id": meeting_id,
          "participant_id": participant_id,
          "source_type": incoming_evidence.source_type,
          "incoming_evidence_id": incoming_evidence.evidence_id,
          "incoming_score": incoming_evidence.score,
          "incoming_reliability": incoming_evidence.reliability,
          "result_confidence": result.confidence if result else None,
          "result_score": result.final_score if result else None,
          "status": status,
          "error_message": error_message,
          "timestamp": now_ms()
      }
      await db[MONGO_FUSION_EVENTS_COL].insert_one(doc)
      return event_id
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save fusion event: {exc}")
      raise FusionStorageError(f"Failed to save fusion event: {exc}") from exc

  @measure_latency("persist_ranking_history")
  async def save_ranking_snapshot(self, ranking: RankingResult) -> None:
    """Append complete meeting ranking snapshot into `ranking_history` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      await db[MONGO_RANKING_HISTORY_COL].insert_one(ranking.model_dump())
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save ranking history: {exc}")
      raise FusionStorageError(f"Failed to save ranking history: {exc}") from exc

  @measure_latency("persist_explanation")
  async def save_explanation(self, explanation: Explanation) -> None:
    """Insert structured rule-based explanation object into `explanations` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return
      await db[MONGO_EXPLANATIONS_COL].insert_one(explanation.model_dump())
    except Exception as exc:
      logger.error(f"FusionPersistence: Failed to save explanation: {exc}")
      raise FusionStorageError(f"Failed to save explanation: {exc}") from exc


fusion_persistence_manager = FusionPersistenceManager()
