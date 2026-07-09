"""
Behavior Engine custom exception hierarchy.

All exceptions derive from BehaviorEngineException for uniform catch clauses
in the pipeline and worker layers.
"""


class BehaviorEngineException(Exception):
  """Base exception for all Behavior Engine errors."""


class FeatureExtractorError(BehaviorEngineException):
  """Raised when behavioral feature extraction fails unexpectedly."""


class MetricCalculationError(BehaviorEngineException):
  """Raised when a specific domain metric calculation fails."""


class TimelineBuilderError(BehaviorEngineException):
  """Raised when assembling or updating the behavioral timeline fails."""


class BehaviorStorageError(BehaviorEngineException):
  """Raised when MongoDB storage operations fail."""


class BehaviorStateError(BehaviorEngineException):
  """Raised when Redis state management operations fail."""


class PipelineExecutionError(BehaviorEngineException):
  """Raised when the top-level behavior pipeline fails."""
