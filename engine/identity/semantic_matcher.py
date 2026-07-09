import logging
from typing import List, Optional

from engine.identity.embedding_client import EmbeddingClient
from engine.identity.config import identity_config
from engine.identity.schemas import SemanticEvidence
from engine.identity.utils import cosine_similarity, embedding_distance
from engine.identity.exceptions import SemanticMatcherError

logger = logging.getLogger("SCIE.identity_engine.semantic_matcher")


class SemanticMatcher:
  """Computes semantic similarity between candidate and participant names
  using Azure OpenAI ``text-embedding-3-large`` embeddings and cosine similarity.

  This module does NOT make candidate decisions.  It only produces SemanticEvidence.

  Semantic similarity catches cases that RapidFuzz misses:
  - Abbreviations (e.g. "William" vs "Will")
  - Transliterations (e.g. "Muhammad" vs "Mohamed")
  - Cross-lingual equivalents (e.g. "Pierre" vs "Peter")
  """

  def __init__(self) -> None:
    self._client = EmbeddingClient.get_instance()

  async def match(
      self,
      candidate_text: Optional[str],
      participant_text: Optional[str],
  ) -> SemanticEvidence:
    """Computes cosine similarity between embeddings of two text inputs.

    Args:
        candidate_text: Normalized candidate name (or any text to compare).
        participant_text: Normalized participant display name.

    Returns:
        SemanticEvidence with cosine_similarity, embedding_distance, score,
        and confidence.  Returns zero-score evidence if embeddings are unavailable.

    Raises:
        SemanticMatcherError: If comparison fails unexpectedly.
    """
    try:
      if not candidate_text or not participant_text:
        return SemanticEvidence(
            score=0.0, confidence=0.0,
            reasons=["Missing candidate or participant text for semantic matching."],
            candidate_text=candidate_text,
            participant_text=participant_text
        )

      # ── Generate both embeddings concurrently ─────────────────────────────
      import asyncio
      c_emb, p_emb = await asyncio.gather(
          self._client.embed(candidate_text),
          self._client.embed(participant_text),
      )

      if c_emb is None or p_emb is None:
        missing = []
        if c_emb is None:
          missing.append("candidate embedding")
        if p_emb is None:
          missing.append("participant embedding")
        logger.warning(
            f"SemanticMatcher: {', '.join(missing)} unavailable — returning zero evidence."
        )
        return SemanticEvidence(
            score=0.0, confidence=0.0,
            reasons=[f"Azure OpenAI unavailable: {', '.join(missing)} could not be generated."],
            candidate_text=candidate_text,
            participant_text=participant_text
        )

      # ── Compute similarity ────────────────────────────────────────────────
      cos_sim = cosine_similarity(c_emb, p_emb)
      emb_dist = embedding_distance(c_emb, p_emb)

      # Normalize cosine similarity [-1, 1] → [0, 1] for scoring purposes
      # Values below MIN_SEMANTIC_SCORE are considered non-matching
      norm_sim = (cos_sim + 1.0) / 2.0   # maps [-1,1] → [0,1]
      raw_score = max(0.0, (cos_sim - identity_config.MIN_SEMANTIC_SCORE) /
                     max(0.01, 1.0 - identity_config.MIN_SEMANTIC_SCORE))

      if cos_sim < identity_config.MIN_SEMANTIC_SCORE:
        logger.debug(
            f"SemanticMatcher: cos_sim={cos_sim:.4f} below threshold "
            f"{identity_config.MIN_SEMANTIC_SCORE} for '{candidate_text}' vs '{participant_text}'"
        )
        return SemanticEvidence(
            score=0.0, confidence=0.0,
            reasons=[
                f"Semantic similarity {cos_sim:.4f} below threshold "
                f"{identity_config.MIN_SEMANTIC_SCORE}."
            ],
            cosine_similarity=round(cos_sim, 4),
            embedding_distance=round(emb_dist, 4),
            candidate_text=candidate_text,
            participant_text=participant_text
        )

      # Map to [0, 1] score: cos_sim=1.0 → score=1.0, threshold → score=0.0
      score = round(min(1.0, raw_score), 4)
      confidence = round(min(1.0, score * (1.05 if cos_sim >= 0.90 else 0.88)), 4)

      logger.debug(
          f"SemanticMatcher: '{candidate_text}' vs '{participant_text}' → "
          f"cos_sim={cos_sim:.4f}, dist={emb_dist:.4f}, score={score:.4f}"
      )

      return SemanticEvidence(
          score=score,
          confidence=confidence,
          reasons=[
              f"Cosine similarity={cos_sim:.4f} between '{candidate_text}' and '{participant_text}' "
              f"(embedding_distance={emb_dist:.4f})"
          ],
          cosine_similarity=round(cos_sim, 4),
          embedding_distance=round(emb_dist, 4),
          embedding_model=identity_config.EMBEDDING_DEPLOYMENT,
          candidate_text=candidate_text,
          participant_text=participant_text
      )

    except Exception as exc:
      raise SemanticMatcherError(f"SemanticMatcher failed: {exc}") from exc
