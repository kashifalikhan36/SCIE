"""
Evidence Fusion Engine custom exception hierarchy.

All exceptions derive from FusionEngineException for uniform catch clauses
in the pipeline, worker, and aggregation layers.
"""


class FusionEngineException(Exception):
  """Base exception for all Evidence Fusion Engine errors."""


class EvidenceAggregationError(FusionEngineException):
  """Raised when incoming evidence fails to merge or aggregate."""


class WeightCalculationError(FusionEngineException):
  """Raised when dynamic weight adjustment or redistribution fails."""


class ScoringError(FusionEngineException):
  """Raised during evidence normalization or reliability scoring."""


class ConfidenceCalculationError(FusionEngineException):
  """Raised when multi-signal confidence score computation fails."""


class RankingError(FusionEngineException):
  """Raised during participant sorting and rank assignment."""


class ExplanationGenerationError(FusionEngineException):
  """Raised when structured explanation building fails."""


class FusionStorageError(FusionEngineException):
  """Raised when MongoDB storage operations fail."""


class FusionStateError(FusionEngineException):
  """Raised when Azure Cache for Redis state operations fail."""


class WorkerExecutionError(FusionEngineException):
  """Raised when background async worker execution fails."""


class DuplicateEvidenceError(FusionEngineException):
  """Raised or signaled when duplicate evidence within a deduplication window is received."""


class MissingParticipantError(FusionEngineException):
  """Raised when operations require an existing participant state that cannot be resolved."""
