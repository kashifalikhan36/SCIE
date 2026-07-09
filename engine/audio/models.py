import os
import logging
from engine.audio.config import audio_config
from engine.audio.constants import (
    VAD_MODEL_NAME,
    DIARIZATION_MODEL_NAME,
    SPEAKER_RECOGNITION_MODEL_NAME,
    LANGUAGE_DETECTION_MODEL_NAME
)

logger = logging.getLogger("SCIE.audio_engine.models")

class ModelRegistry:
  _instance = None

  def __init__(self):
    self.vad_model = None
    self.diarization_model = None
    self.speaker_recognition_model = None
    self.language_detection_model = None
    
    # Track initialization status
    self.vad_loaded = False
    self.diarization_loaded = False
    self.speaker_rec_loaded = False
    self.lang_det_loaded = False

  @classmethod
  def get_instance(cls):
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def initialize_all(self):
    """Attempt to load all models into memory."""
    self.load_vad()
    self.load_diarization()
    self.load_speaker_recognition()
    self.load_language_detection()

  def load_vad(self):
    """Load Voice Activity Detection model."""
    if self.vad_loaded:
      return
    try:
      logger.info(f"Loading VAD model: {VAD_MODEL_NAME}...")
      # Attempt lazy import
      from pyannote.audio import Model
      # Pyannote models often require auth token
      self.vad_model = Model.from_pretrained(
          VAD_MODEL_NAME, 
          use_auth_token=audio_config.HF_TOKEN or True
      )
      self.vad_loaded = True
      logger.info("VAD model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load VAD model ({e}). Pipeline will use fallback heuristic VAD.")
      self.vad_model = None
      self.vad_loaded = False

  def load_diarization(self):
    """Load Speaker Diarization model."""
    if self.diarization_loaded:
      return
    try:
      logger.info(f"Loading Diarization model: {DIARIZATION_MODEL_NAME}...")
      from pyannote.audio import Pipeline
      self.diarization_model = Pipeline.from_pretrained(
          DIARIZATION_MODEL_NAME, 
          use_auth_token=audio_config.HF_TOKEN or True
      )
      self.diarization_loaded = True
      logger.info("Diarization model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load Diarization model ({e}). Pipeline will use fallback heuristic Diarization.")
      self.diarization_model = None
      self.diarization_loaded = False

  def load_speaker_recognition(self):
    """Load Speaker Recognition embedding model."""
    if self.speaker_rec_loaded:
      return
    try:
      logger.info(f"Loading Speaker Recognition model: {SPEAKER_RECOGNITION_MODEL_NAME}...")
      from speechbrain.inference.speaker import EncoderClassifier
      # Use CPU if CUDA is not available or has problems
      import torch
      run_opts = {"device": "cuda"} if torch.cuda.is_available() else {"device": "cpu"}
      
      self.speaker_recognition_model = EncoderClassifier.from_hparams(
          source=SPEAKER_RECOGNITION_MODEL_NAME, 
          run_opts=run_opts
      )
      self.speaker_rec_loaded = True
      logger.info("Speaker Recognition model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load Speaker Recognition model ({e}). Pipeline will use mock speaker embedding.")
      self.speaker_recognition_model = None
      self.speaker_rec_loaded = False

  def load_language_detection(self):
    """Load Language Detection model."""
    if self.lang_det_loaded:
      return
    try:
      logger.info(f"Loading Language Detection model: {LANGUAGE_DETECTION_MODEL_NAME}...")
      from speechbrain.inference.classifiers import EncoderClassifier
      import torch
      run_opts = {"device": "cuda"} if torch.cuda.is_available() else {"device": "cpu"}
      
      self.language_detection_model = EncoderClassifier.from_hparams(
          source=LANGUAGE_DETECTION_MODEL_NAME, 
          run_opts=run_opts
      )
      self.lang_det_loaded = True
      logger.info("Language Detection model loaded successfully.")
    except Exception as e:
      logger.warning(f"Could not load Language Detection model ({e}). Pipeline will use fallback language detector.")
      self.language_detection_model = None
      self.lang_det_loaded = False
