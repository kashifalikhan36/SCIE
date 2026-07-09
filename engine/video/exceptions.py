class VideoEngineException(Exception):
  """Base exception for all Video Engine errors."""
  pass

class VideoReaderError(VideoEngineException):
  """Exception raised by the Video Reader."""
  pass

class FrameBufferError(VideoEngineException):
  """Exception raised by the Frame Buffer."""
  pass

class FaceDetectionError(VideoEngineException):
  """Exception raised by the Face Detector."""
  pass

class FaceCropperError(VideoEngineException):
  """Exception raised by the Face Cropper."""
  pass

class FaceTrackingError(VideoEngineException):
  """Exception raised by the Tracker."""
  pass

class RecognitionError(VideoEngineException):
  """Exception raised by the InsightFace Recognizer."""
  pass

class EmbeddingStoreError(VideoEngineException):
  """Exception raised by the Embedding Store."""
  pass

class ComparatorError(VideoEngineException):
  """Exception raised by the Embedding Comparator."""
  pass

class StorageError(VideoEngineException):
  """Exception raised by MongoDB storage."""
  pass
