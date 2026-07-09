import logging
from typing import List

from engine.transcript.schemas import TranscriptChunk, ConversationTurn
from engine.transcript.config import transcript_config
from engine.transcript.utils import count_words, generate_turn_id, compute_avg_wpm
from engine.transcript.exceptions import ConversationBuilderError

logger = logging.getLogger("SCIE.transcript_engine.conversation_builder")


class ConversationBuilder:
  """Groups finalized utterances into structured conversational turns.

  A new ``ConversationTurn`` begins when:

  - The speaker changes, OR
  - The same speaker pauses for longer than ``CONVERSATION_TURN_GAP_SEC``.

  Each turn carries ``avg_confidence``, ``avg_wpm``, and a sequential
  ``turn_index`` so downstream engines (GPT reasoning, Behavior Engine) can
  reason over the conversation without reprocessing raw chunks.
  """

  def build_conversation_turns(
      self,
      finalized_chunks: List[TranscriptChunk],
  ) -> List[ConversationTurn]:
    """Groups *finalized_chunks* into ``ConversationTurn`` objects.

    Parameters
    ----------
    finalized_chunks:
        Unordered list of finalized ``TranscriptChunk`` objects.  The
        builder sorts them internally.

    Returns
    -------
    List[ConversationTurn]
        Ordered list of conversation turns; empty if input is empty.

    Raises
    ------
    ConversationBuilderError
        If grouping fails due to an unexpected error.
    """
    if not finalized_chunks:
      return []

    try:
      ordered = sorted(finalized_chunks, key=lambda c: c.start_time)

      turns: List[ConversationTurn] = []
      turn_index = 0

      # ── Initialise the first turn ──────────────────────────────────────
      first = ordered[0]
      current_speaker      = first.speaker_id
      current_utterances   = [first.text]
      current_start        = first.start_time
      current_end          = first.end_time
      current_confidences  = [first.confidence]
      current_word_counts  = [count_words(first.text)]
      current_durations    = [max(0.0, first.end_time - first.start_time)]

      for chunk in ordered[1:]:
        gap = chunk.start_time - current_end
        same_speaker = chunk.speaker_id == current_speaker
        within_gap   = gap <= transcript_config.CONVERSATION_TURN_GAP_SEC

        if same_speaker and within_gap:
          # Extend the current turn
          current_utterances.append(chunk.text)
          current_end = max(current_end, chunk.end_time)
          current_confidences.append(chunk.confidence)
          current_word_counts.append(count_words(chunk.text))
          current_durations.append(max(0.0, chunk.end_time - chunk.start_time))
        else:
          # Seal the current turn and start a new one
          turns.append(
              self._build_turn(
                  turn_index=turn_index,
                  speaker_id=current_speaker,
                  utterances=current_utterances,
                  start_time=current_start,
                  end_time=current_end,
                  confidences=current_confidences,
                  word_counts=current_word_counts,
                  durations=current_durations,
              )
          )
          turn_index += 1

          # Start next turn
          current_speaker     = chunk.speaker_id
          current_utterances  = [chunk.text]
          current_start       = chunk.start_time
          current_end         = chunk.end_time
          current_confidences = [chunk.confidence]
          current_word_counts = [count_words(chunk.text)]
          current_durations   = [max(0.0, chunk.end_time - chunk.start_time)]

      # Seal the final turn
      turns.append(
          self._build_turn(
              turn_index=turn_index,
              speaker_id=current_speaker,
              utterances=current_utterances,
              start_time=current_start,
              end_time=current_end,
              confidences=current_confidences,
              word_counts=current_word_counts,
              durations=current_durations,
          )
      )

      logger.debug(
          f"ConversationBuilder: Grouped {len(ordered)} utterances "
          f"into {len(turns)} turns."
      )
      return turns

    except Exception as exc:
      raise ConversationBuilderError(
          f"Failed to group conversation turns: {exc}"
      ) from exc

  # ── Private helpers ───────────────────────────────────────────────────────

  @staticmethod
  def _build_turn(
      turn_index: int,
      speaker_id: str,
      utterances: List[str],
      start_time: float,
      end_time: float,
      confidences: List[float],
      word_counts: List[int],
      durations: List[float],
  ) -> ConversationTurn:
    """Constructs a fully-populated ``ConversationTurn`` from accumulators."""
    total_words    = sum(word_counts)
    total_duration = max(0.0, end_time - start_time)
    avg_conf       = sum(confidences) / len(confidences) if confidences else 0.0
    avg_wpm        = compute_avg_wpm(total_words, total_duration)

    return ConversationTurn(
        conversation_turn_id=generate_turn_id(),
        turn_index=turn_index,
        speaker_id=speaker_id,
        utterances=utterances,
        start_time=start_time,
        end_time=end_time,
        duration=total_duration,
        word_count=total_words,
        avg_wpm=round(avg_wpm, 2),
        avg_confidence=round(avg_conf, 4),
    )
