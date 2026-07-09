"""
Conversation Analyzer for the Conversation Reasoning Engine.

Responsibilities:
- Build chronological speaker conversation timelines from ConversationTurn objects.
- Maintain accurate speaker attribution, timestamps, durations, and turns.
- Segment long meetings into bounded ConversationChunk slices (by N turns or 5-minute durations)
  to optimize Azure OpenAI context windows.
"""
from typing import List, Set
from engine.transcript.schemas import ConversationTurn
from engine.conversation.config import conversation_config
from engine.conversation.models import ConversationChunk
from engine.conversation.utils import generate_chunk_id


class ConversationAnalyzer:
  """Formats and chunks conversation turns for semantic prompt reasoning."""

  @classmethod
  def format_turn_timestamp(cls, sec: float) -> str:
    """Format seconds into HH:MM:SS format."""
    s = int(sec)
    hours = s // 3600
    minutes = (s % 3600) // 60
    seconds = s % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

  @classmethod
  def build_timeline_text(cls, turns: List[ConversationTurn]) -> str:
    """Format a list of ConversationTurns into a human and model-readable timeline string."""
    if not turns:
      return ""

    lines = []
    for turn in turns:
      start_str = cls.format_turn_timestamp(turn.start_time)
      end_str = cls.format_turn_timestamp(turn.end_time)
      text = " ".join(turn.utterances).strip()
      if not text:
        continue
      lines.append(f"[{start_str} - {end_str}] {turn.speaker_id}:\n{text}\n")

    return "\n".join(lines)

  @classmethod
  def chunk_conversation(
      cls,
      turns: List[ConversationTurn],
      max_turns: Optional[int] = None,
      max_seconds: Optional[float] = None
  ) -> List[ConversationChunk]:
    """Split a chronological list of ConversationTurns into bounded ConversationChunks.

    A chunk boundary occurs when either ``max_turns`` is reached or the time elapsed
    within the current chunk exceeds ``max_seconds``.
    """
    if not turns:
      return []

    limit_turns = max_turns if max_turns is not None else conversation_config.CHUNK_SIZE_TURNS
    limit_sec = max_seconds if max_seconds is not None else conversation_config.CHUNK_SIZE_SECONDS

    # Ensure turns are sorted
    sorted_turns = sorted(turns, key=lambda t: (t.turn_index, t.start_time))
    meeting_id = sorted_turns[0].meeting_id if hasattr(sorted_turns[0], "meeting_id") else "unknown_meeting"

    chunks: List[ConversationChunk] = []
    current_turns: List[ConversationTurn] = []
    chunk_start_time: float = -1.0
    speakers_in_chunk: Set[str] = set()

    for turn in sorted_turns:
      if chunk_start_time < 0:
        chunk_start_time = turn.start_time

      elapsed = turn.end_time - chunk_start_time
      # Check boundary conditions
      if len(current_turns) >= limit_turns or (len(current_turns) > 0 and elapsed > limit_sec):
        # Flush chunk
        formatted_text = cls.build_timeline_text(current_turns)
        if formatted_text:
          chunks.append(
              ConversationChunk(
                  chunk_id=generate_chunk_id(),
                  meeting_id=meeting_id,
                  turn_index_start=current_turns[0].turn_index,
                  turn_index_end=current_turns[-1].turn_index,
                  start_time=current_turns[0].start_time,
                  end_time=current_turns[-1].end_time,
                  turn_count=len(current_turns),
                  formatted_text=formatted_text,
                  speakers=sorted(list(speakers_in_chunk))
              )
          )
        current_turns = [turn]
        chunk_start_time = turn.start_time
        speakers_in_chunk = {turn.speaker_id}
      else:
        current_turns.append(turn)
        speakers_in_chunk.add(turn.speaker_id)

    # Flush remaining turns
    if current_turns:
      formatted_text = cls.build_timeline_text(current_turns)
      if formatted_text:
        chunks.append(
            ConversationChunk(
                chunk_id=generate_chunk_id(),
                meeting_id=meeting_id,
                turn_index_start=current_turns[0].turn_index,
                turn_index_end=current_turns[-1].turn_index,
                start_time=current_turns[0].start_time,
                end_time=current_turns[-1].end_time,
                turn_count=len(current_turns),
                formatted_text=formatted_text,
                speakers=sorted(list(speakers_in_chunk))
            )
        )

    return chunks
