class TranscriptEngineException(Exception):
  """Base exception for all Transcript Engine errors."""
  pass

class TranscriptReceiverError(TranscriptEngineException):
  """Exception raised by the Transcript Receiver."""
  pass

class TranscriptBufferError(TranscriptEngineException):
  """Exception raised by the Transcript Buffer."""
  pass

class PartialManagerError(TranscriptEngineException):
  """Exception raised by the Partial Transcript Manager."""
  pass

class FinalManagerError(TranscriptEngineException):
  """Exception raised by the Final Transcript Manager."""
  pass

class TimelineBuilderError(TranscriptEngineException):
  """Exception raised by the Speaker Timeline Builder."""
  pass

class ConversationBuilderError(TranscriptEngineException):
  """Exception raised by the Conversation Builder."""
  pass

class EvidenceProviderError(TranscriptEngineException):
  """Exception raised by the Transcript Evidence Provider."""
  pass

class StorageError(TranscriptEngineException):
  """Exception raised by MongoDB storage."""
  pass
