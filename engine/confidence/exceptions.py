"""
Uniform Exception Hierarchy for the SCIE Confidence Engine (`engine/confidence/`).

Provides clean, structured exception classes with context mapping across
validation, normalization, dynamic weighting, calculation, and storage operations.
(`engine/confidence/exceptions.py`)
"""
from typing import Optional, Dict, Any


class ConfidenceEngineException(Exception):
  """Base exception for all Confidence Engine failures."""
  def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
    super().__init__(message)
    self.message = message
    self.details = details or {}


class ConfidenceValidationError(ConfidenceEngineException):
  """Raised when incoming evidence fails boundary, ID, or source check."""
  pass


class ConfidenceNormalizationError(ConfidenceEngineException):
  """Raised during errors in score normalization routines."""
  pass


class ConfidenceWeightError(ConfidenceEngineException):
  """Raised when weight profiles are invalid, negative, or fail normalization."""
  pass


class ConfidenceCalculationError(ConfidenceEngineException):
  """Raised during calculation strategy evaluation errors."""
  pass


class ConfidenceStorageError(ConfidenceEngineException):
  """Raised when Redis or MongoDB persistence operations encounter critical faults."""
  pass
