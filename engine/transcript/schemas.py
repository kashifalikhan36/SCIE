from pydantic import BaseModel, Field
from typing import List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Input / Streaming schema
# ──────────────────────────────────────────────────────────────────────────────

class TranscriptChunk(BaseModel):
  """Representation of a single streaming transcript event from the Audio Engine.

  Partial chunks (``is_final=False``) are rolling updates from Whisper's
  streaming output and may be superseded by later chunks with the same
  speaker and overlapping timestamps.  Final chunks (``is_final=True``) are
  immutable and must be archived.
  """

  meeting_id:  str
  speaker_id:  str
  text:        str
  start_time:  float
  end_time:    float
  confidence:  float
  is_final:    bool
  timestamp:   int   # Epoch milliseconds of Audio Engine emission


# ──────────────────────────────────────────────────────────────────────────────
# Builder output schemas
# ──────────────────────────────────────────────────────────────────────────────

class SpeakerTimelineEntry(BaseModel):
  """A single entry in the chronological speaker conversation timeline.

  Supports both attribute access (``entry.transcript``) and dict-style
  subscript access (``entry["transcript"]``) for backward compatibility with
  code that treats timeline entries as plain dicts.
  """

  speaker_id:  str
  start_time:  float
  end_time:    float
  duration:    float = Field(..., ge=0.0)
  transcript:  str
  confidence:  float

  def __getitem__(self, item: str):
    """Enable dict-style access: ``entry["transcript"]``."""
    return getattr(self, item)



class SpeakerStats(BaseModel):
  """Cumulative per-speaker metrics computed by the Timeline Builder.

  Consumed by downstream Behavior Engine and Evidence Fusion Engine.
  """

  speaker_id:         str
  utterance_count:    int   = 0
  total_speaking_time: float = 0.0  # seconds
  avg_wpm:            float = 0.0   # average words per minute across utterances
  avg_confidence:     float = 0.0


class ConversationTurn(BaseModel):
  """Abstraction grouping contiguous speaker utterances into a single turn.

  Future GPT reasoning engines should consume ``ConversationTurn`` objects
  rather than raw ``TranscriptChunk`` objects.
  """

  conversation_turn_id: str = Field(default="")
  turn_index:           int = Field(default=0, description="Zero-based sequential turn index across the meeting")
  speaker_id:           str
  utterances:           List[str]
  start_time:           float
  end_time:             float
  duration:             float = Field(..., ge=0.0)
  word_count:           int
  avg_wpm:              float = 0.0
  avg_confidence:       float = 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Engine output schema
# ──────────────────────────────────────────────────────────────────────────────

class TranscriptEvidence(BaseModel):
  """Primary output object of the Transcript Engine.

  Consumed by:
  - Participant Association Engine
  - Behavior Engine
  - Conversation Reasoning Engine (GPT-5.5)
  - Evidence Fusion Engine

  The ``transcript_search_keywords`` field is pre-populated for future
  keyword / semantic search without requiring a schema migration.
  """

  meeting_id:                str
  speaker_id:                str
  conversation_turn_id:      str
  text:                      str
  start_time:                float
  end_time:                  float
  duration:                  float = Field(..., ge=0.0)
  word_count:                int
  avg_wpm:                   float = 0.0
  confidence:                float
  is_final:                  bool
  timestamp:                 int   # Epoch milliseconds of evidence assembly
  transcript_search_keywords: List[str] = Field(
      default_factory=list,
      description="Significant words (≥4 chars) extracted for future keyword/semantic search"
  )


# ──────────────────────────────────────────────────────────────────────────────
# Redis state schema
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantTranscriptState(BaseModel):
  """Live participant transcript state cached in Redis.

  Always contains the most recent partial and final text alongside
  cumulative speaking stats.  Entries expire automatically via Redis TTL.
  """

  speaker_id:           str
  latest_partial:       Optional[str] = None
  latest_final:         Optional[str] = None
  conversation_history: List[str]     = Field(default_factory=list)
  last_updated:         int           # Epoch ms
  word_count:           int           = 0
  speaking_duration:    float         = 0.0   # seconds
  avg_wpm:              float         = 0.0
