import logging
from typing import List, Optional

from rapidfuzz import fuzz, distance as rfuzz_distance

from engine.identity.normalizer import NameNormalizer
from engine.identity.nickname_resolver import NicknameResolver
from engine.identity.config import identity_config
from engine.identity.schemas import FuzzyEvidence
from engine.identity.exceptions import FuzzyMatcherError

logger = logging.getLogger("SCIE.identity_engine.fuzzy_matcher")


class FuzzyMatcher:
  """RapidFuzz-based name similarity matcher.

  Compares candidate name variants (including aliases) against participant
  display names using multiple RapidFuzz strategies:

  * ``WRatio`` — best overall similarity metric
  * ``token_sort_ratio`` — order-invariant token comparison
  * ``partial_ratio`` — substring containment
  * ``Levenshtein.distance`` — raw edit distance for explainability

  Returns FuzzyEvidence containing the best score, edit distance, matched
  tokens, and which name variant produced the match.

  This module does NOT make candidate decisions.
  """

  def __init__(self) -> None:
    self._normalizer = NameNormalizer()
    self._resolver = NicknameResolver()

  def match(
      self,
      candidate_name: Optional[str],
      participant_name: Optional[str],
      candidate_variants: Optional[List[str]] = None,
  ) -> FuzzyEvidence:
    """Compares candidate_name against participant_name using RapidFuzz.

    Also tests all known alias variants of candidate_name automatically if
    ``candidate_variants`` is not provided.

    Args:
        candidate_name: Expected candidate name from meeting metadata.
        participant_name: Observed participant display name.
        candidate_variants: Optional pre-computed alias list.  If omitted,
            the NicknameResolver generates them.

    Returns:
        FuzzyEvidence with best score across all strategies and variants.

    Raises:
        FuzzyMatcherError: If the matching operation fails.
    """
    try:
      if not candidate_name or not participant_name:
        missing = []
        if not candidate_name:
          missing.append("candidate name")
        if not participant_name:
          missing.append("participant name")
        return FuzzyEvidence(
            score=0.0, confidence=0.0,
            reasons=[f"Missing {' and '.join(missing)}."]
        )

      norm_candidate = self._normalizer.normalize(candidate_name)
      norm_participant = self._normalizer.normalize(participant_name)

      if not norm_candidate or not norm_participant:
        return FuzzyEvidence(
            score=0.0, confidence=0.0,
            reasons=["Empty string after normalization."]
        )

      # Build all candidate variants to test
      variants = candidate_variants if candidate_variants else self._resolver.expand(candidate_name)
      if norm_candidate not in variants:
        variants = [norm_candidate] + list(variants)

      best_score = 0.0
      best_variant = None
      best_edit = 0
      best_tokens: List[str] = []
      best_reasons: List[str] = []

      for variant in variants:
        if not variant:
          continue

        # Multiple RapidFuzz metrics
        wratio = fuzz.WRatio(variant, norm_participant) / 100.0
        token_sort = fuzz.token_sort_ratio(variant, norm_participant) / 100.0
        partial = fuzz.partial_ratio(variant, norm_participant) / 100.0
        # Weighted combination: WRatio highest weight
        combined = max(wratio, token_sort, partial * 0.85)

        # Edit distance for explainability
        edit = rfuzz_distance.Levenshtein.distance(variant, norm_participant)

        if combined > best_score:
          best_score = combined
          best_variant = variant
          best_edit = edit
          best_tokens = [t for t in variant.split() if t in norm_participant.split()]
          best_reasons = [
              f"WRatio='{wratio:.2f}', token_sort='{token_sort:.2f}', partial='{partial:.2f}' "
              f"between '{variant}' and '{norm_participant}'"
          ]

      if best_score < identity_config.MIN_FUZZY_SCORE:
        return FuzzyEvidence(
            score=round(best_score, 4),
            confidence=0.0,
            reasons=[
                f"Best fuzzy score {best_score:.2f} below threshold "
                f"{identity_config.MIN_FUZZY_SCORE} for '{candidate_name}' vs '{participant_name}'."
            ]
        )

      # Confidence scales with score (high similarity → high confidence)
      confidence = round(min(1.0, best_score * (1.10 if best_score >= 0.85 else 0.90)), 4)

      reasons = best_reasons + [
          f"Best variant: '{best_variant}' (edit_distance={best_edit})"
      ]

      logger.debug(
          f"FuzzyMatcher: '{candidate_name}' vs '{participant_name}' → "
          f"score={best_score:.4f}, conf={confidence:.4f}, variant='{best_variant}'"
      )

      return FuzzyEvidence(
          score=round(best_score, 4),
          confidence=confidence,
          reasons=reasons,
          similarity=round(best_score, 4),
          edit_distance=best_edit,
          matched_tokens=best_tokens,
          matched_variant=best_variant
      )

    except Exception as exc:
      raise FuzzyMatcherError(f"FuzzyMatcher failed: {exc}") from exc
