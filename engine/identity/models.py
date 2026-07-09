"""
Model registry for the Identity Engine.

Holds references to any optional ML models (e.g. a spaCy NER model,
sentence-transformer, etc.) that may be loaded in the future.

Currently manages the Azure OpenAI client lifecycle used by EmbeddingClient.
"""
import logging
from typing import Optional

logger = logging.getLogger("SCIE.identity_engine.models")


class IdentityModelRegistry:
  """Process-wide singleton managing optional model state for the Identity Engine.

  Centralizes any heavy initialization that should only happen once per process.
  Downstream modules call ``IdentityModelRegistry.get_instance()`` instead of
  importing directly so that tests can cleanly mock or reset the registry.
  """

  _instance: Optional["IdentityModelRegistry"] = None

  def __init__(self) -> None:
    self._ready = False

  @classmethod
  def get_instance(cls) -> "IdentityModelRegistry":
    """Returns the process-wide singleton, creating it if necessary."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def is_ready(self) -> bool:
    """Returns True once the registry has been fully initialized."""
    return self._ready

  def initialize(self) -> None:
    """Performs one-time initialization of shared model state.

    Called automatically by the pipeline on first use.
    Safe to call multiple times (idempotent).
    """
    if self._ready:
      return
    logger.info("IdentityModelRegistry: Initialized (no external models required at startup).")
    self._ready = True
