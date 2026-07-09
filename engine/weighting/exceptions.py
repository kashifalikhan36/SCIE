"""
Uniform exception hierarchy for the SCIE Dynamic Weighting Engine.

(`engine/weighting/exceptions.py`)
"""


class WeightingEngineException(Exception):
  """Base exception for all errors raised within the Dynamic Weighting Engine."""
  pass


class EvidenceValidationError(WeightingEngineException):
  """Raised when incoming evidence payloads are corrupted, invalid, or malformed."""
  pass


class QualityEvaluationError(WeightingEngineException):
  """Raised when quality metric evaluation fails or encounters invalid boundaries."""
  pass


class StrategyEvaluationError(WeightingEngineException):
  """Raised when strategy selection or dynamic rule evaluation encounters errors."""
  pass


class WeightNormalizationError(WeightingEngineException):
  """Raised when weight normalization fails (e.g., all domains unavailable yielding 0 sum)."""
  pass


class StorageError(WeightingEngineException):
  """Raised when persistence operations to Redis or MongoDB fail."""
  pass
