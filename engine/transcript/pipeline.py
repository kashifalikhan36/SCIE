import logging
import uuid
from typing import Dict, List, Optional

from engine.transcript.schemas import (
    ConversationTurn,
    TranscriptChunk,
    TranscriptEvidence,
)
from engine.transcript.receiver import TranscriptReceiver
from engine.transcript.buffer import TranscriptBuffer
from engine.transcript.partial_manager import PartialTranscriptManager
from engine.transcript.final_manager import FinalTranscriptManager
from engine.transcript.timeline_builder import SpeakerTimelineBuilder
from engine.transcript.conversation_builder import ConversationBuilder
from engine.transcript.transcript_provider import TranscriptEvidenceProvider
from engine.transcript.participant_state import ParticipantTranscriptStateManager
from engine.transcript.storage import TranscriptStorageManager
from engine.transcript.logger import measure_latency

logger = logging.getLogger("SCIE.transcript_engine.pipeline")


class TranscriptEnginePipeline:
  """Orchestrates the full transcript processing pipeline.

  Data flow
  ---------
  Audio Engine → raw event dict
      └─ Receiver       (validate + normalise)
      └─ Buffer         (chronological ordering + dedup)
      └─ Partial Manager  or  Final Manager  (routing on is_final)
      └─ Timeline Builder  +  Conversation Builder  (on final)
      └─ Evidence Provider  (assemble TranscriptEvidence)
      └─ Participant State Manager  (update Redis)
      └─ Storage Manager  (persist to MongoDB)
      └─ → TranscriptEvidence  (returned to caller / worker)

  Error handling
  --------------
  Each pipeline stage is wrapped independently.  A failure in any single
  stage produces a structured log entry and either falls back gracefully or
  returns ``None`` — the pipeline **never** crashes the worker process.

  Concurrency
  -----------
  The pipeline instance is shared by all worker tasks in a single process.
  All state is either per-meeting (keyed in Redis / MongoDB) or per-call
  local variables; there is no shared mutable state inside the pipeline.
  """

  def __init__(self) -> None:
    self.receiver         = TranscriptReceiver()
    self.buffer           = TranscriptBuffer()
    self.partial_manager  = PartialTranscriptManager()
    self.final_manager    = FinalTranscriptManager()
    self.timeline_builder = SpeakerTimelineBuilder()
    self.conv_builder     = ConversationBuilder()
    self.state_manager    = ParticipantTranscriptStateManager()
    self.storage_manager  = TranscriptStorageManager()

  @measure_latency("transcript_pipeline.process_chunk")
  async def process_chunk(
      self,
      meeting_id: str,
      raw_chunk_data: dict,
  ) -> Optional[TranscriptEvidence]:
    """Processes a single raw transcript event through the full pipeline.

    Parameters
    ----------
    meeting_id:
        Meeting scope (used for storage + Redis key routing).
    raw_chunk_data:
        Raw dictionary from the Audio Engine (Whisper output).

    Returns
    -------
    Optional[TranscriptEvidence]
        Structured evidence on success; ``None`` on validation failure or
        unrecoverable error.
    """

    # ── Stage 1: Receiver — validate and normalise ─────────────────────────
    try:
      chunk = self.receiver.receive_event(raw_chunk_data)
    except Exception as exc:
      logger.warning(f"Pipeline[Stage 1/Receiver]: Rejected chunk — {exc}")
      return None

    # ── Stage 2: Raw event persistence ────────────────────────────────────
    try:
      await self.storage_manager.save_raw_event(meeting_id, raw_chunk_data)
      await self.storage_manager.save_meeting_info(meeting_id, {"status": "active"})
    except Exception as exc:
      logger.error(f"Pipeline[Stage 2/RawPersist]: Failed to log raw event — {exc}")
      # Non-fatal: continue the pipeline

    # ── Stage 3: Buffer — chronological ordering ───────────────────────────
    try:
      self.buffer.add_chunk(chunk)
    except Exception as exc:
      logger.error(f"Pipeline[Stage 3/Buffer]: Failed to buffer chunk — {exc}")
      # Treat the chunk as if it came directly; don't drop it
      pass

    # ── Stage 4: Route on is_final ─────────────────────────────────────────
    if not chunk.is_final:
      return await self._process_partial(meeting_id, chunk)
    else:
      return await self._process_final(meeting_id, chunk)

  # ── Partial path ──────────────────────────────────────────────────────────

  async def _process_partial(
      self,
      meeting_id: str,
      chunk: TranscriptChunk,
  ) -> Optional[TranscriptEvidence]:
    """Handles a rolling partial chunk (is_final=False)."""

    # Stage 4a: Update rolling partial in Redis
    try:
      await self.partial_manager.update_partial(
          meeting_id, chunk.speaker_id, chunk.text
      )
      logger.info(
          f"Pipeline[Partial]: Updated rolling partial — "
          f"speaker={chunk.speaker_id}, text='{chunk.text[:60]}'"
      )
    except Exception as exc:
      logger.error(f"Pipeline[Partial/Redis]: Failed to update partial — {exc}")

    # Stage 4b: Build a temporary rolling ConversationTurn for the evidence object
    rolling_turn = ConversationTurn(
        conversation_turn_id="turn_rolling",
        turn_index=0,
        speaker_id=chunk.speaker_id,
        utterances=[chunk.text],
        start_time=chunk.start_time,
        end_time=chunk.end_time,
        duration=max(0.0, chunk.end_time - chunk.start_time),
        word_count=0,
        avg_wpm=0.0,
        avg_confidence=chunk.confidence,
    )

    # Stage 4c: Assemble evidence
    try:
      evidence = TranscriptEvidenceProvider.assemble_evidence(
          meeting_id, chunk, rolling_turn
      )
    except Exception as exc:
      logger.error(f"Pipeline[Partial/Evidence]: Assembly failed — {exc}")
      return None

    # Stage 4d: Update Redis live state
    try:
      await self.state_manager.update_state(meeting_id, evidence)
    except Exception as exc:
      logger.error(f"Pipeline[Partial/State]: Redis update failed — {exc}")

    return evidence

  # ── Final path ────────────────────────────────────────────────────────────

  async def _process_final(
      self,
      meeting_id: str,
      chunk: TranscriptChunk,
  ) -> Optional[TranscriptEvidence]:
    """Handles a finalized chunk (is_final=True)."""

    # Stage 4a: Archive in FinalManager, get full ordered history
    try:
      final_history = await self.final_manager.finalize_utterance(meeting_id, chunk)
      logger.info(
          f"Pipeline[Final]: Archived utterance — "
          f"speaker={chunk.speaker_id}, history_len={len(final_history)}"
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Archive]: Failed to finalize utterance — {exc}")
      final_history = [chunk]

    # Stage 4b: Build speaker timeline
    try:
      timeline = self.timeline_builder.build_timeline(final_history)
      await self.storage_manager.save_timeline(meeting_id, timeline)
      logger.debug(
          f"Pipeline[Final/Timeline]: Saved {len(timeline)}-entry timeline."
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Timeline]: Timeline build failed — {exc}")
      timeline = []

    # Stage 4c: Compute and persist speaker stats
    try:
      stats_map = self.timeline_builder.build_speaker_stats(final_history)
      for stats in stats_map.values():
        await self.storage_manager.save_speaker_stats(meeting_id, stats)
      logger.debug(
          f"Pipeline[Final/Stats]: Persisted stats for "
          f"{len(stats_map)} speaker(s)."
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Stats]: Speaker stats build failed — {exc}")

    # Stage 4d: Build conversation turns
    try:
      turns = self.conv_builder.build_conversation_turns(final_history)
      for turn in turns:
        await self.storage_manager.save_conversation_turn(meeting_id, turn)
      logger.debug(
          f"Pipeline[Final/Turns]: Built and saved {len(turns)} conversation turn(s)."
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Turns]: Conversation build failed — {exc}")
      turns = []

    # Stage 4e: Find the ConversationTurn containing this chunk's text.
    # We match by speaker_id and time overlap, which is robust to whitespace
    # normalisation differences.  Fall back to a synthetic turn if none match.
    matching_turn = self._find_matching_turn(chunk, turns)

    # Stage 4f: Assemble TranscriptEvidence
    try:
      evidence = TranscriptEvidenceProvider.assemble_evidence(
          meeting_id, chunk, matching_turn
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Evidence]: Assembly failed — {exc}")
      return None

    # Stage 4g: Update Redis live state
    try:
      await self.state_manager.update_state(meeting_id, evidence)
    except Exception as exc:
      logger.error(f"Pipeline[Final/State]: Redis state update failed — {exc}")

    # Stage 4h: Persist finalized transcript segment to MongoDB
    try:
      await self.storage_manager.save_finalized_transcript(
          meeting_id=meeting_id,
          speaker_id=chunk.speaker_id,
          text=chunk.text,
          start=chunk.start_time,
          end=chunk.end_time,
          timestamp=chunk.timestamp,
      )
    except Exception as exc:
      logger.error(f"Pipeline[Final/Persist]: Failed to persist transcript — {exc}")

    # Stage 4i: Persist structured TranscriptEvidence
    try:
      await self.storage_manager.save_transcript_evidence(evidence)
    except Exception as exc:
      logger.error(f"Pipeline[Final/Evidence/Persist]: Failed to persist evidence — {exc}")

    return evidence

  # ── Private helpers ───────────────────────────────────────────────────────

  @staticmethod
  def _find_matching_turn(
      chunk: TranscriptChunk,
      turns: List[ConversationTurn],
  ) -> ConversationTurn:
    """Finds the ``ConversationTurn`` that temporally contains *chunk*.

    Matching strategy (in order of preference):
    1. Turn where ``start_time ≤ chunk.start_time ≤ end_time`` and same speaker.
    2. Turn from the same speaker closest in start_time.
    3. Synthetic fallback turn so the pipeline never returns None.

    This is robust to whitespace normalisation differences and avoids the
    fragile ``chunk.text in utterances`` substring check.
    """
    if not turns:
      return TranscriptEnginePipeline._synthetic_turn(chunk)

    # Strategy 1 — temporal overlap with same speaker
    for turn in turns:
      if (
          turn.speaker_id == chunk.speaker_id
          and turn.start_time <= chunk.start_time <= turn.end_time
      ):
        return turn

    # Strategy 2 — closest-start same-speaker turn
    same_speaker_turns = [t for t in turns if t.speaker_id == chunk.speaker_id]
    if same_speaker_turns:
      return min(
          same_speaker_turns,
          key=lambda t: abs(t.start_time - chunk.start_time),
      )

    # Strategy 3 — last turn in the list (final fallback)
    return turns[-1]

  @staticmethod
  def _synthetic_turn(chunk: TranscriptChunk) -> ConversationTurn:
    """Creates a minimal synthetic turn when no real turns exist."""
    return ConversationTurn(
        conversation_turn_id=f"turn_{uuid.uuid4().hex[:8]}",
        turn_index=0,
        speaker_id=chunk.speaker_id,
        utterances=[chunk.text],
        start_time=chunk.start_time,
        end_time=chunk.end_time,
        duration=max(0.0, chunk.end_time - chunk.start_time),
        word_count=0,
        avg_wpm=0.0,
        avg_confidence=chunk.confidence,
    )
