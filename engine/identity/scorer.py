import logging
from typing import List, Optional, Tuple

from engine.identity.config import identity_config
from engine.identity.schemas import (
    EmailEvidence,
    FuzzyEvidence,
    SemanticEvidence,
    AliasEvidence,
    MetadataEvidence,
)
from engine.identity.exceptions import IdentityScorerError

logger = logging.getLogger("SCIE.identity_engine.scorer")


class IdentityScorer:
  """Combines all evidence signals into a single identity score and confidence.

  Weighting strategy (all configurable via ``identity_config``):

  =========  ============  ===========================================
  Signal     Weight        Rationale
  =========  ============  ===========================================
  Email      0.30          Deterministic; very high specificity
  Semantic   0.25          Catches nicknames / transliterations
  Fuzzy      0.20          Robust to typos and formatting variants
  Alias      0.15          Explicit nickname resolution
  Metadata   0.10          Supporting corroboration
  =========  ============  ===========================================

  Active-weight normalization: only evidences that contributed a non-zero
  score participate in the weighted sum.  This prevents partial signal updates
  from artificially deflating the overall score.

  Multi-modal boost: when ≥ 3 independent signals align with score ≥ 0.50,
  confidence is boosted by 1.10×.

  This module does NOT make candidate decisions.
  """

  def calculate(
      self,
      email_evidence: Optional[EmailEvidence] = None,
      fuzzy_evidence: Optional[FuzzyEvidence] = None,
      semantic_evidence: Optional[SemanticEvidence] = None,
      alias_evidence: Optional[AliasEvidence] = None,
      metadata_evidence: Optional[MetadataEvidence] = None,
  ) -> Tuple[float, float, List[str]]:
    """Calculates the overall (identity_score, confidence, aggregated_reasons).

    Args:
        email_evidence: Evidence from EmailMatcher.
        fuzzy_evidence: Evidence from FuzzyMatcher (RapidFuzz).
        semantic_evidence: Evidence from SemanticMatcher (Azure OpenAI).
        alias_evidence: Evidence from NicknameResolver.
        metadata_evidence: Evidence from MetadataMatcher.

    Returns:
        Tuple of (identity_score, confidence, reasons_list).

    Raises:
        IdentityScorerError: If the calculation fails unexpectedly.
    """
    try:
      total_weighted_score = 0.0
      total_weighted_conf = 0.0
      active_weight_sum = 0.0
      aggregated_reasons: List[str] = []

      weight_map = [
          (email_evidence,    identity_config.WEIGHT_EMAIL,    "Email"),
          (semantic_evidence, identity_config.WEIGHT_SEMANTIC, "Semantic"),
          (fuzzy_evidence,    identity_config.WEIGHT_FUZZY,    "Fuzzy"),
          (alias_evidence,    identity_config.WEIGHT_ALIAS,    "Alias"),
          (metadata_evidence, identity_config.WEIGHT_METADATA, "Metadata"),
      ]

      active_signal_count = 0

      for evidence, weight, label in weight_map:
        if evidence is None:
          continue
        # Include in calculation only if it carries a meaningful signal
        if evidence.score > 0.0 or evidence.confidence > 0.0:
          total_weighted_score += evidence.score * weight
          total_weighted_conf += evidence.confidence * weight
          active_weight_sum += weight
          active_signal_count += 1
          for r in evidence.reasons:
            prefixed = f"[{label}] {r}"
            if r and prefixed not in aggregated_reasons:
              aggregated_reasons.append(prefixed)

      if active_weight_sum <= 0.0:
        return 0.0, 0.0, ["No active identity evidence signals."]

      # Normalize by active weight sum
      norm_score = round(min(1.0, total_weighted_score / active_weight_sum), 4)
      norm_conf = round(min(1.0, total_weighted_conf / active_weight_sum), 4)

      # Count strong signals (score >= 0.50) for multi-modal boost
      strong_signals = sum(
          1 for ev, _, _ in weight_map
          if ev is not None and ev.score >= 0.50
      )
      if strong_signals >= 3:
        norm_conf = round(min(1.0, norm_conf * 1.10), 4)
        norm_score = round(min(1.0, norm_score * 1.05), 4)
        aggregated_reasons.append(
            f"[Scorer] Multi-modal alignment boost: {strong_signals} strong signals agree."
        )
      elif strong_signals == 2:
        norm_conf = round(min(1.0, norm_conf * 1.03), 4)

      logger.debug(
          f"IdentityScorer: score={norm_score:.4f}, conf={norm_conf:.4f}, "
          f"active_signals={active_signal_count}, strong={strong_signals}"
      )
      return norm_score, norm_conf, aggregated_reasons

    except Exception as exc:
      raise IdentityScorerError(f"IdentityScorer failed: {exc}") from exc
