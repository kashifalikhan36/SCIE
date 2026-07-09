"""
Identity Engine custom exception hierarchy.

All exceptions derive from IdentityEngineException for uniform catch clauses
in the pipeline and worker layers.
"""


class IdentityEngineException(Exception):
  """Base exception for all Identity Engine errors."""


class NormalizationError(IdentityEngineException):
  """Raised when name normalization fails unexpectedly."""


class NicknameResolverError(IdentityEngineException):
  """Raised when alias/nickname resolution encounters an error."""


class EmailMatcherError(IdentityEngineException):
  """Raised when email comparison fails."""


class MetadataMatcherError(IdentityEngineException):
  """Raised when metadata comparison fails."""


class FuzzyMatcherError(IdentityEngineException):
  """Raised when RapidFuzz matching fails."""


class EmbeddingClientError(IdentityEngineException):
  """Raised when the Azure OpenAI embedding client fails."""


class EmbeddingTimeoutError(EmbeddingClientError):
  """Raised when an embedding request times out."""


class SemanticMatcherError(IdentityEngineException):
  """Raised when semantic similarity calculation fails."""


class IdentityScorerError(IdentityEngineException):
  """Raised when the identity scorer fails to calculate a score."""


class IdentityStateError(IdentityEngineException):
  """Raised when Redis state management operations fail."""


class IdentityStorageError(IdentityEngineException):
  """Raised when MongoDB persistence operations fail."""


class IdentityPipelineError(IdentityEngineException):
  """Raised when the identity pipeline fails to process a request."""
