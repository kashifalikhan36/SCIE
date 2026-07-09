"""
engine.transcript
=================

Production-ready Transcript Engine for the SCIE backend.

Responsibilities
----------------
- Receive streaming transcript events from the Audio Engine (Whisper / Groq).
- Buffer, deduplicate, and order partial and final transcript chunks.
- Merge rolling partial transcripts intelligently.
- Archive finalized utterances immutably.
- Build a chronological speaker timeline with cumulative stats.
- Group utterances into structured ConversationTurn objects.
- Produce TranscriptEvidence objects for downstream engines.
- Maintain live transcript state in Azure Cache for Redis.
- Persist all historical data to MongoDB.

Public API
----------
The most commonly used symbols are exported here for convenient import:

    from engine.transcript import (
        TranscriptEngineWorkerManager,
        enqueue_transcript_event,
        TranscriptEnginePipeline,
        transcript_config,
        TranscriptChunk,
        TranscriptEvidence,
        ConversationTurn,
        SpeakerStats,
        SpeakerTimelineEntry,
    )
"""

from engine.transcript.workers import TranscriptEngineWorkerManager, enqueue_transcript_event
from engine.transcript.pipeline import TranscriptEnginePipeline
from engine.transcript.config import transcript_config
from engine.transcript.schemas import (
    TranscriptChunk,
    TranscriptEvidence,
    ConversationTurn,
    ParticipantTranscriptState,
    SpeakerStats,
    SpeakerTimelineEntry,
)

__all__ = [
    # Worker management
    "TranscriptEngineWorkerManager",
    "enqueue_transcript_event",

    # Pipeline
    "TranscriptEnginePipeline",

    # Configuration
    "transcript_config",

    # Schemas (consumed by Audio Engine and downstream engines)
    "TranscriptChunk",
    "TranscriptEvidence",
    "ConversationTurn",
    "ParticipantTranscriptState",
    "SpeakerStats",
    "SpeakerTimelineEntry",
]
