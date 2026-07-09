import logging
from engine.transcript.schemas import TranscriptChunk, ConversationTurn, TranscriptEvidence
from engine.transcript.utils import count_words, compute_avg_wpm, extract_search_keywords, now_ms
from engine.transcript.exceptions import EvidenceProviderError

logger = logging.getLogger("SCIE.transcript_engine.transcript_provider")


class TranscriptEvidenceProvider:
  """Assembles pipeline outputs into a unified ``TranscriptEvidence`` object.

  This is the final step of the Transcript Engine pipeline.  The resulting
  ``TranscriptEvidence`` is the canonical output consumed by:

  - Participant Association Engine
  - Behavior Engine
  - Conversation Reasoning Engine (GPT-5.5)
  - Evidence Fusion Engine

  The provider is intentionally stateless so it can be called concurrently
  for multiple meetings without synchronisation overhead.
  """

  @staticmethod
  def assemble_evidence(
      meeting_id: str,
      chunk: TranscriptChunk,
      associated_turn: ConversationTurn,
  ) -> TranscriptEvidence:
    """Assembles a ``TranscriptEvidence`` from a chunk and its conversation turn.

    Parameters
    ----------
    meeting_id:
        Scoping identifier for the meeting.
    chunk:
        The processed ``TranscriptChunk`` (partial or final).
    associated_turn:
        The ``ConversationTurn`` that contains this chunk's utterance.

    Returns
    -------
    TranscriptEvidence
        Fully-populated evidence object.

    Raises
    ------
    EvidenceProviderError
        If assembly fails for any reason.
    """
    try:
      duration  = max(0.0, chunk.end_time - chunk.start_time)
      words     = count_words(chunk.text)
      avg_wpm   = compute_avg_wpm(words, duration)
      keywords  = extract_search_keywords(chunk.text)

      evidence = TranscriptEvidence(
          meeting_id=meeting_id,
          speaker_id=chunk.speaker_id,
          conversation_turn_id=associated_turn.conversation_turn_id,
          text=chunk.text,
          start_time=chunk.start_time,
          end_time=chunk.end_time,
          duration=duration,
          word_count=words,
          avg_wpm=round(avg_wpm, 2),
          confidence=chunk.confidence,
          is_final=chunk.is_final,
          timestamp=now_ms(),
          transcript_search_keywords=keywords,
      )

      logger.debug(
          f"TranscriptEvidenceProvider: Assembled evidence — "
          f"meeting={meeting_id}, speaker={chunk.speaker_id}, "
          f"is_final={chunk.is_final}, turn={associated_turn.conversation_turn_id}, "
          f"text='{chunk.text[:50]}'"
      )
      return evidence

    except Exception as exc:
      raise EvidenceProviderError(
          f"Failed to assemble TranscriptEvidence for speaker {chunk.speaker_id}: {exc}"
      ) from exc
