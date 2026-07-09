import logging
from engine.video.config import video_config
from engine.video.constants import MEDIAPIPE_FACE_DETECTION, INSIGHTFACE_RECOGNITION

logger = logging.getLogger("SCIE.video_engine.models")

class ModelRegistry:
  """Singleton registry managing lazy initialization of computer vision models."""
  _instance = None

  def __init__(self):
    self.detector_model = None
    self.detector_loaded = False
    
    self.recognizer_model = None
    self.recognizer_loaded = False

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def load_all_models(self):
    """Triggers synchronous loading of all configured models."""
    self.load_face_detector()
    self.load_face_recognizer()

  def load_face_detector(self):
    """Loads MediaPipe Face Detection model."""
    if self.detector_loaded:
      return
      
    try:
      logger.info("Initializing MediaPipe Face Detection model...")
      import mediapipe as mp
      self.mp_face_detection = mp.solutions.face_detection
      
      # Instantiate the detector with configuration parameters
      self.detector_model = self.mp_face_detection.FaceDetection(
          min_detection_confidence=video_config.MIN_FACE_CONFIDENCE,
          model_selection=0 # 0 for short-range faces (within 2m), 1 for full range
      )
      self.detector_loaded = True
      logger.info("MediaPipe Face Detection model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load MediaPipe Face Detector ({e}). Pipeline will use fallback detector.")
      self.detector_model = None
      self.detector_loaded = False

  def load_face_recognizer(self):
    """Loads InsightFace Face Analysis and extraction model."""
    if self.recognizer_loaded:
      return
      
    try:
      logger.info("Initializing InsightFace Face Recognition model...")
      import insightface
      # Buffalo_l is the standard lightweight model pack
      app = insightface.app.FaceAnalysis(name="buffalo_l")
      # Prepare on CPU by default (-1 for CPU, 0+ for CUDA device index)
      app.prepare(ctx_id=-1, det_size=(640, 640))
      
      self.recognizer_model = app
      self.recognizer_loaded = True
      logger.info("InsightFace Face Recognition model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load InsightFace model ({e}). Pipeline will use mock recognition embeddings.")
      self.recognizer_model = None
      self.recognizer_loaded = False
