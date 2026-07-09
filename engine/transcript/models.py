import logging

logger = logging.getLogger("SCIE.transcript_engine.models")


class TranscriptModelRegistry:
  """Registry managing configuration contexts and optional future NLP models.

  The Transcript Engine currently requires no local ML model weights —
  transcription is handled upstream by Whisper (Audio Engine / Groq).

  This registry is a forward-compatibility hook.  Future additions may
  include:
  - Sentence segmentation models (e.g. spaCy, NLTK)
  - Language-specific text normalizers
  - Punctuation restoration models for raw ASR output
  - Keyword / topic extraction models for search indexing

  All downstream engines should obtain models through ``get_instance()``
  rather than instantiating them directly so that lazy loading and
  singleton guarantees are preserved.
  """

  _instance = None

  def __init__(self):
    self.models_loaded: bool = True
    # Future NLP model slots (None until loaded)
    self.sentence_segmenter = None
    self.keyword_extractor   = None
    self.punctuation_restorer = None

  @classmethod
  def get_instance(cls) -> "TranscriptModelRegistry":
    """Returns the singleton TranscriptModelRegistry instance."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def load_models(self) -> None:
    """No local model weights are required in the current implementation.

    Override this method to lazily load NLP models when they become
    available (e.g. spaCy for sentence segmentation).
    """
    logger.debug("TranscriptModelRegistry: No local model weights needed at this stage.")

  def is_ready(self) -> bool:
    """Returns True when the registry is initialised and ready to serve."""
    return self.models_loaded
