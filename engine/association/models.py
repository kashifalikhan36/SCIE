import logging
from typing import Optional, List
from engine.association.utils import cosine_similarity

logger = logging.getLogger("SCIE.association_engine.models")


class AssociationModelRegistry:
  """Singleton registry managing optional sentence embedding models.

  By default, the MetadataMatcher uses RapidFuzz fuzzy string matching which
  is deterministic and fast. If sentence embeddings (e.g., sentence-transformers)
  are loaded into this registry, the matcher can optionally compute semantic
  embedding similarities between metadata fields.
  """

  _instance: Optional["AssociationModelRegistry"] = None

  def __init__(self):
    self.sentence_model = None
    self.models_loaded: bool = True

  @classmethod
  def get_instance(cls) -> "AssociationModelRegistry":
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def load_models(self) -> None:
    """Lazily loads sentence embedding models if available."""
    logger.debug("AssociationModelRegistry: Defaulting to RapidFuzz deterministic string matching.")

  def compute_text_similarity(self, text1: str, text2: str) -> Optional[float]:
    """Computes semantic embedding similarity if sentence model is loaded."""
    if not self.sentence_model or not text1 or not text2:
      return None
    try:
      emb1 = self.sentence_model.encode(text1)
      emb2 = self.sentence_model.encode(text2)
      return cosine_similarity(list(emb1), list(emb2))
    except Exception as exc:
      logger.warning(f"AssociationModelRegistry: Sentence embedding check failed ({exc})")
      return None
