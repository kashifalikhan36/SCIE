import time
import logging
from typing import Dict, Any, List
from engine.video.utils import calculate_cosine_similarity
from engine.video.exceptions import ComparatorError

logger = logging.getLogger("SCIE.video_engine.comparator")

class EmbeddingComparator:
  """Compares face embeddings and measures similarity metrics using cosine distance."""

  def compare(self, embedding_a: List[float], embedding_b: List[float]) -> Dict[str, Any]:
    """Compares two embeddings and returns a dictionary of metrics."""
    try:
      similarity = calculate_cosine_similarity(embedding_a, embedding_b)
      # Cosine distance is defined as 1 - similarity
      distance = max(0.0, 1.0 - similarity)
      
      # Confidence indicator based on similarity strength
      confidence = float(similarity) if similarity > 0 else 0.0

      return {
          "similarity_score": similarity,
          "confidence": confidence,
          "distance": distance,
          "comparison_timestamp": int(time.time() * 1000)
      }
    except Exception as e:
      raise ComparatorError(f"Failed to compare embeddings: {e}")
