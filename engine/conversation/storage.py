"""
MongoDB Storage Manager for the Conversation Reasoning Engine.

Responsibilities:
- Persist structured reasoning evidence across 4 distinct collections:
  * ``conversation_reasoning``: Summary snapshots of full reasoning execution passes.
  * ``conversation_evidence``: Append-only individual ConversationEvidence items.
  * ``reasoning_history``: Chronological history of speaker role profiles over time.
  * ``prompt_history``: Audit logs tracking latency, token usage, and prompt/model versions.
- Ensure append-only, non-overwriting historical preservation.
"""
import uuid
from typing import List, Dict, Any, Optional
from database.mongodb import get_mongo_db
from engine.conversation.constants import (
    MONGO_CONVERSATION_REASONING_COL,
    MONGO_CONVERSATION_EVIDENCE_COL,
    MONGO_REASONING_HISTORY_COL,
    MONGO_PROMPT_HISTORY_COL,
)
from engine.conversation.schemas import (
    ConversationEvidence,
    ConversationReasoningSnapshot,
    PromptHistoryRecord,
)
from engine.conversation.exceptions import ConversationStorageError
from engine.conversation.utils import now_ms
from engine.conversation.logger import logger


class ConversationStorageManager:
  """Async MongoDB manager for conversation reasoning persistence."""

  async def save_evidence_item(self, evidence: ConversationEvidence) -> None:
    """Insert a single ConversationEvidence object into ``conversation_evidence`` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return

      doc = evidence.model_dump()
      await db[MONGO_CONVERSATION_EVIDENCE_COL].insert_one(doc)
      logger.debug(f"Storage: Saved evidence {evidence.evidence_id} ({evidence.evidence_type}) for {evidence.speaker_id}")
    except Exception as exc:
      logger.error(f"Storage: Failed to save evidence item {evidence.evidence_id}: {exc}")
      raise ConversationStorageError(f"Failed to save evidence: {exc}") from exc

  async def save_evidence_batch(self, evidence_list: List[ConversationEvidence]) -> None:
    """Batch insert multiple ConversationEvidence objects cleanly."""
    if not evidence_list:
      return
    try:
      db = get_mongo_db()
      if db is None:
        return

      docs = [e.model_dump() for e in evidence_list]
      await db[MONGO_CONVERSATION_EVIDENCE_COL].insert_many(docs)
      logger.debug(f"Storage: Batch saved {len(docs)} evidence items.")
    except Exception as exc:
      logger.error(f"Storage: Failed batch save of evidence: {exc}")
      raise ConversationStorageError(f"Failed to save evidence batch: {exc}") from exc

  async def save_reasoning_snapshot(
      self,
      meeting_id: str,
      evidence_count: int,
      speaker_count: int,
      chunk_id: Optional[str] = None
  ) -> ConversationReasoningSnapshot:
    """Insert a summary snapshot of a reasoning pass into ``conversation_reasoning`` collection."""
    try:
      db = get_mongo_db()
      snapshot = ConversationReasoningSnapshot(
          snapshot_id=f"CRS_{uuid.uuid4().hex[:8]}",
          meeting_id=meeting_id,
          chunk_id=chunk_id,
          evidence_count=evidence_count,
          speaker_count=speaker_count,
          timestamp=now_ms()
      )
      if db is not None:
        await db[MONGO_CONVERSATION_REASONING_COL].insert_one(snapshot.model_dump())
        logger.debug(f"Storage: Saved reasoning snapshot {snapshot.snapshot_id}")
      return snapshot
    except Exception as exc:
      logger.error(f"Storage: Failed to save reasoning snapshot: {exc}")
      raise ConversationStorageError(f"Failed to save snapshot: {exc}") from exc

  async def save_reasoning_history(
      self,
      meeting_id: str,
      speaker_id: str,
      evidence_map: Dict[str, Any],
      confidence: float,
      summary: str,
      timestamp: Optional[int] = None
  ) -> None:
    """Append a historical record of a speaker's reasoning profile into ``reasoning_history`` collection."""
    try:
      db = get_mongo_db()
      if db is None:
        return

      doc = {
          "history_id": f"CRH_{uuid.uuid4().hex[:8]}",
          "meeting_id": meeting_id,
          "speaker_id": speaker_id,
          "evidence_map": evidence_map,
          "confidence": confidence,
          "summary": summary,
          "timestamp": timestamp or now_ms()
      }
      await db[MONGO_REASONING_HISTORY_COL].insert_one(doc)
      logger.debug(f"Storage: Saved reasoning history for {speaker_id}")
    except Exception as exc:
      logger.error(f"Storage: Failed to save reasoning history for {speaker_id}: {exc}")
      raise ConversationStorageError(f"Failed to save history: {exc}") from exc

  async def save_prompt_history(
      self,
      meeting_id: str,
      chunk_id: str,
      prompt_type: str,
      prompt_version: str,
      model_version: str,
      latency_ms: float,
      tokens_used: int,
      status: str = "SUCCESS",
      error_message: Optional[str] = None
  ) -> PromptHistoryRecord:
    """Insert prompt audit metadata into ``prompt_history`` collection."""
    try:
      db = get_mongo_db()
      record = PromptHistoryRecord(
          record_id=f"CPH_{uuid.uuid4().hex[:8]}",
          meeting_id=meeting_id,
          chunk_id=chunk_id,
          prompt_type=prompt_type,
          prompt_version=prompt_version,
          model_version=model_version,
          latency_ms=latency_ms,
          tokens_used=tokens_used,
          status=status,
          error_message=error_message,
          timestamp=now_ms()
      )
      if db is not None:
        await db[MONGO_PROMPT_HISTORY_COL].insert_one(record.model_dump())
        logger.debug(f"Storage: Saved prompt history record {record.record_id}")
      return record
    except Exception as exc:
      logger.error(f"Storage: Failed to save prompt history: {exc}")
      raise ConversationStorageError(f"Failed to save prompt history: {exc}") from exc
