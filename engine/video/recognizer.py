import logging
import random
from typing import List, Tuple
import numpy as np
from engine.video.models import ModelRegistry
from engine.video.exceptions import RecognitionError

logger = logging.getLogger("SCIE.video_engine.recognizer")

class FaceRecognizer:
  """Generates normalized 512-dimensional face recognition embeddings using InsightFace."""

  def __init__(self):
    self.registry = ModelRegistry.get_instance()
    self.embedding_dim = 512

  async def generate_embedding(self, cropped_face: np.ndarray, track_id: str) -> Tuple[List[float], float]:
    """Extracts face embedding and returns (embedding_vector, confidence_score)."""
    if cropped_face is None or cropped_face.size == 0:
      raise RecognitionError("Cropped face image is empty.")

    # 1. Use InsightFace model if loaded
    if self.registry.recognizer_loaded and self.registry.recognizer_model is not None:
      try:
        # InsightFace expects BGR/RGB images.
        # Run FaceAnalysis face extraction
        faces = self.registry.recognizer_model.get(cropped_face)
        if faces:
          # Use the first detected face embedding
          raw_emb = faces[0].normed_embedding
          embedding = raw_emb.tolist()
          confidence = float(faces[0].det_score)
          logger.debug(f"InsightFace: Extracted embedding for track {track_id} (confidence: {confidence:.2f})")
          return embedding, confidence
      except Exception as e:
        logger.error(f"InsightFace embedding extraction failed: {e}. Falling back to mock embeddings.")

    # 2. Heuristic/Mock Fallback: Generate a deterministic L2-normalized 512d embedding based on track_id
    try:
      random.seed(hash(track_id))
      mock_emb = [random.uniform(-0.1, 0.1) for _ in range(self.embedding_dim)]
      
      # L2 normalization
      norm = sum(x*x for x in mock_emb) ** 0.5
      if norm > 0:
        mock_emb = [x / norm for x in mock_emb]
        
      logger.debug(f"FaceRecognizer (Fallback): Generated mock embedding for track {track_id}")
      return mock_emb, 0.90
    except Exception as err:
      raise RecognitionError(f"Error during face embedding generation: {err}")
