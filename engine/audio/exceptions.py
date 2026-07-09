class AudioEngineException(Exception):
  """Base exception for all Audio Engine errors."""
  pass

class AudioReaderError(AudioEngineException):
  """Exception raised by the Audio Reader."""
  pass

class AudioBufferError(AudioEngineException):
  """Exception raised by the Audio Buffer."""
  pass

class VADError(AudioEngineException):
  """Exception raised by the VAD component."""
  pass

class DiarizationError(AudioEngineException):
  """Exception raised by the Diarization component."""
  pass

class SpeakerRecognitionError(AudioEngineException):
  """Exception raised by the Speaker Recognition component."""
  pass

class TranscriberError(AudioEngineException):
  """Exception raised by the Whisper Transcriber."""
  pass

class LanguageDetectorError(AudioEngineException):
  """Exception raised by the Language Detector."""
  pass

class StorageError(AudioEngineException):
  """Exception raised by Database or Redis storage components."""
  pass
