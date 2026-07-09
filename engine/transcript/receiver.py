import logging
from engine.transcript.schemas import TranscriptChunk
from engine.transcript.config import transcript_config
from engine.transcript.utils import normalize_text
from engine.transcript.exceptions import TranscriptReceiverError

logger = logging.getLogger("SCIE.transcript_engine.receiver")


class TranscriptReceiver:
  """Validates and normalises raw transcript event dicts from the Audio Engine.

  Responsibilities
  ----------------
  - Validate schema via Pydantic (``TranscriptChunk.model_validate``).
  - Reject events with missing or logically invalid fields.
  - Normalise text (collapse whitespace, strip).
  - Enforce the minimum confidence threshold from config.
  - Preserve event ordering — this class is stateless; ordering is the
    caller's responsibility.
  - Support multiple concurrent meetings — all operations are pure
    (no shared state).

  This receiver never silently swallows events.  Callers must handle
  ``TranscriptReceiverError`` and decide whether to log-and-skip or
  propagate.
  """

  def receive_event(self, event_data: dict) -> TranscriptChunk:
    """Validates, sanitises, and returns a verified ``TranscriptChunk``.

    Parameters
    ----------
    event_data:
        Raw dictionary from the Audio Engine pipeline.

    Returns
    -------
    TranscriptChunk
        Validated and normalised chunk ready for buffering.

    Raises
    ------
    TranscriptReceiverError
        If the event is malformed, missing required fields, or below the
        configured confidence threshold.
    """
    try:
      # 1. Pydantic validation — catches type errors and missing fields
      chunk = TranscriptChunk.model_validate(event_data)

      # 2. Semantic field validation
      if not chunk.meeting_id:
        raise TranscriptReceiverError("Rejection: meeting_id is missing or empty.")
      if not chunk.speaker_id:
        raise TranscriptReceiverError("Rejection: speaker_id is missing or empty.")
      if chunk.start_time < 0.0:
        raise TranscriptReceiverError(
            f"Rejection: start_time is negative ({chunk.start_time})."
        )
      if chunk.end_time < chunk.start_time:
        raise TranscriptReceiverError(
            f"Rejection: end_time ({chunk.end_time}) is before start_time ({chunk.start_time})."
        )

      # 3. Text normalisation — collapse whitespace, strip padding
      normalised_text = normalize_text(chunk.text)
      if not normalised_text:
        raise TranscriptReceiverError("Rejection: transcript text is empty after normalisation.")

      # Rebuild chunk with normalised text (Pydantic models are immutable by
      # default so we use model_copy).
      chunk = chunk.model_copy(update={"text": normalised_text})

      # 4. Confidence filter
      if chunk.confidence < transcript_config.MIN_CONFIDENCE_THRESHOLD:
        logger.info(
            "Receiver: Filtered low-confidence chunk "
            f"(speaker={chunk.speaker_id}, "
            f"conf={chunk.confidence:.2f} < threshold={transcript_config.MIN_CONFIDENCE_THRESHOLD:.2f})"
        )
        raise TranscriptReceiverError(
            f"Rejection: confidence {chunk.confidence:.2f} is below the configured threshold "
            f"({transcript_config.MIN_CONFIDENCE_THRESHOLD:.2f})."
        )

      logger.debug(
          f"Receiver: Validated chunk — meeting={chunk.meeting_id}, "
          f"speaker={chunk.speaker_id}, is_final={chunk.is_final}, "
          f"text='{chunk.text[:40]}...'"
      )
      return chunk

    except TranscriptReceiverError:
      raise
    except Exception as exc:
      raise TranscriptReceiverError(f"Malformed transcript event data: {exc}") from exc
