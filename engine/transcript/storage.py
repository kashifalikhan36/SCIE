import logging
from typing import Any, Dict, List

from database.mongodb import get_mongo_db
from engine.transcript.schemas import (
    ConversationTurn,
    SpeakerStats,
    SpeakerTimelineEntry,
    TranscriptEvidence,
)
from engine.transcript.constants import (
    MONGO_EVENTS_COL,
    MONGO_EVIDENCE_COL,
    MONGO_MEETINGS_COL,
    MONGO_SPEAKER_STATS_COL,
    MONGO_TIMELINES_COL,
    MONGO_TRANSCRIPTS_COL,
    MONGO_TURNS_COL,
)
from engine.transcript.exceptions import StorageError

logger = logging.getLogger("SCIE.transcript_engine.storage")


class TranscriptStorageManager:
  """Handles all MongoDB persistence for the Transcript Engine.

  Design principles
  -----------------
  - **Append-only** for transcripts and events (use ``insert_one``).
  - **Upsert-based** for meeting metadata, timelines, turns, and stats
    (idempotent, safe to replay).
  - **Separate collections** for raw transcripts vs structured evidence —
    avoids mixed-schema documents and makes future semantic search simpler.
  - **Never overwrite history** — all finalized data is immutable.
  - **Future search-ready** — ``meeting_id + speaker_id + start`` compound
    index hints are documented on every query for the DBA team.

  Collections
  -----------
  ``meetings``            — Meeting status / metadata  (upsert)
  ``transcripts``         — Raw finalized text segments  (upsert by key)
  ``conversation_turns``  — Grouped ConversationTurn objects  (upsert by turn_id)
  ``speaker_timelines``   — Full ordered timeline per meeting  (upsert)
  ``transcript_events``   — Raw un-aggregated event log  (insert)
  ``transcript_evidence`` — Structured TranscriptEvidence records  (insert)
  ``speaker_stats``       — Cumulative per-speaker metrics  (upsert)
  """

  # ── Meeting metadata ───────────────────────────────────────────────────────

  async def save_meeting_info(
      self,
      meeting_id: str,
      metadata: Dict[str, Any],
  ) -> None:
    """Persists or updates meeting status / metadata."""
    db = get_mongo_db()
    if db is None:
      logger.warning("Storage: MongoDB unavailable — skipping meeting info save.")
      return
    try:
      await db[MONGO_MEETINGS_COL].update_one(
          {"meeting_id": meeting_id},
          {"$set": {**metadata, "meeting_id": meeting_id}},
          upsert=True,
      )
      logger.debug(f"Storage: Upserted meeting metadata for meeting={meeting_id}")
    except Exception as exc:
      logger.error(f"Storage: Failed to save meeting metadata: {exc}")

  # ── Raw event log ──────────────────────────────────────────────────────────

  async def save_raw_event(
      self,
      meeting_id: str,
      event_data: Dict[str, Any],
  ) -> None:
    """Appends a raw transcript event dict to the event log collection.

    This is an immutable audit log — never modified after insertion.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      await db[MONGO_EVENTS_COL].insert_one({**event_data, "meeting_id": meeting_id})
      logger.debug("Storage: Inserted raw transcript event.")
    except Exception as exc:
      logger.error(f"Storage: Failed to insert raw transcript event: {exc}")

  # ── Finalized transcript segments ─────────────────────────────────────────

  async def save_finalized_transcript(
      self,
      meeting_id: str,
      speaker_id: str,
      text: str,
      start: float,
      end: float,
      timestamp: int,
  ) -> None:
    """Persists a finalized transcript segment.

    Uses ``$setOnInsert`` to be idempotent — a re-delivered final event
    will not overwrite an already-stored segment.

    The compound key ``(meeting_id, speaker_id, start, timestamp)`` is the
    natural index; DBA should ensure an index exists on these fields.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      await db[MONGO_TRANSCRIPTS_COL].update_one(
          {
              "meeting_id": meeting_id,
              "speaker_id": speaker_id,
              "start":      start,
              "timestamp":  timestamp,
          },
          {"$setOnInsert": {
              "meeting_id": meeting_id,
              "speaker_id": speaker_id,
              "text":       text,
              "start":      start,
              "end":        end,
              "timestamp":  timestamp,
              "is_final":   True,        # ← fixes existing test assertion
          }},
          upsert=True,
      )
      logger.debug(
          f"Storage: Persisted finalized transcript for speaker={speaker_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Failed to save finalized transcript: {exc}")

  # ── Conversation turns ─────────────────────────────────────────────────────

  async def save_conversation_turn(
      self,
      meeting_id: str,
      turn: ConversationTurn,
  ) -> None:
    """Upserts a ``ConversationTurn`` by its ``conversation_turn_id``."""
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = turn.model_dump()
      await db[MONGO_TURNS_COL].update_one(
          {
              "meeting_id":           meeting_id,
              "conversation_turn_id": turn.conversation_turn_id,
          },
          {"$set": {**doc, "meeting_id": meeting_id}},
          upsert=True,
      )
      logger.debug(
          f"Storage: Upserted conversation turn {turn.conversation_turn_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Failed to save conversation turn: {exc}")

  # ── Speaker timeline ───────────────────────────────────────────────────────

  async def save_timeline(
      self,
      meeting_id: str,
      timeline: list,
  ) -> None:
    """Upserts the full ordered speaker timeline for a meeting.

    Accepts either a list of ``SpeakerTimelineEntry`` Pydantic objects or a
    list of plain dicts (for backward compatibility with callers that build
    the timeline manually).

    The timeline is stored as a single document with a ``timeline`` array
    field so it can be retrieved and rendered atomically.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      # Accept both Pydantic SpeakerTimelineEntry objects and plain dicts
      serialised = [
          entry.model_dump() if hasattr(entry, "model_dump") else entry
          for entry in timeline
      ]
      await db[MONGO_TIMELINES_COL].update_one(
          {"meeting_id": meeting_id},
          {"$set": {"meeting_id": meeting_id, "timeline": serialised}},
          upsert=True,
      )
      logger.debug(
          f"Storage: Upserted speaker timeline with {len(timeline)} entries "
          f"for meeting={meeting_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Failed to save speaker timeline: {exc}")

  # ── Structured evidence ────────────────────────────────────────────────────

  async def save_transcript_evidence(
      self,
      evidence: TranscriptEvidence,
  ) -> None:
    """Inserts a ``TranscriptEvidence`` record into its own collection.

    Kept separate from ``transcripts`` to avoid mixed schemas and to allow
    independent indexing strategies for evidence vs raw text queries.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = evidence.model_dump()
      await db[MONGO_EVIDENCE_COL].insert_one(doc)
      logger.info(
          f"Storage: Persisted TranscriptEvidence for "
          f"speaker={evidence.speaker_id}, meeting={evidence.meeting_id}"
      )
    except Exception as exc:
      logger.error(f"Storage: Failed to insert transcript evidence: {exc}")

  # ── Speaker stats ──────────────────────────────────────────────────────────

  async def save_speaker_stats(
      self,
      meeting_id: str,
      stats: SpeakerStats,
  ) -> None:
    """Upserts cumulative per-speaker metrics for a meeting.

    Overwrites the previous stats snapshot so callers always have the
    latest cumulative figures without growing the collection unboundedly.
    """
    db = get_mongo_db()
    if db is None:
      return
    try:
      doc = stats.model_dump()
      await db[MONGO_SPEAKER_STATS_COL].update_one(
          {"meeting_id": meeting_id, "speaker_id": stats.speaker_id},
          {"$set": {**doc, "meeting_id": meeting_id}},
          upsert=True,
      )
      logger.info(
          f"Storage: Upserted SpeakerStats — "
          f"speaker={stats.speaker_id}, utterances={stats.utterance_count}, "
          f"avg_wpm={stats.avg_wpm}"
      )
    except Exception as exc:
      logger.error(f"Storage: Failed to save speaker stats: {exc}")
