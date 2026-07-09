"""
Specific exception hierarchy for the Participant Identity Resolution Engine.
All exceptions derive from AssociationEngineException so callers can catch
pipeline-wide errors cleanly.
"""


class AssociationEngineException(Exception):
  """Base exception for all Participant Identity Resolution Engine errors."""
  pass


class MatcherError(AssociationEngineException):
  """Base class for errors occurring during evidence matching."""
  pass


class MetadataMatcherError(MatcherError):
  """Raised when the MetadataMatcher encounters malformed or unprocessable input."""
  pass


class TranscriptMatcherError(MatcherError):
  """Raised when the TranscriptMatcher fails to process transcript evidence."""
  pass


class SpeakerMatcherError(MatcherError):
  """Raised when the SpeakerMatcher fails to correlate speaker evidence."""
  pass


class TrackMatcherError(MatcherError):
  """Raised when the TrackMatcher fails to correlate visual track evidence."""
  pass


class TimelineMatcherError(MatcherError):
  """Raised when the TimelineMatcher encounters temporal correlation errors."""
  pass


class StateManagementError(AssociationEngineException):
  """Raised when Azure Cache for Redis state synchronization fails."""
  pass


class ConfidenceCalculationError(AssociationEngineException):
  """Raised when confidence score computation fails or receives invalid weights."""
  pass


class AssociationStorageError(AssociationEngineException):
  """Raised when historical association persistence to MongoDB fails."""
  pass
