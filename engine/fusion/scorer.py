"""
Evidence Scorer for the Evidence Fusion Engine (`engine/fusion/`).

Normalizes domain evidence scores onto a strictly bounded [0, 1] scale and
incorporates signal reliability to compute effective scores and diagnostic reasons.
"""
from typing import Dict, List
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.constants import (
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT,
    EvidenceStatus
)
from engine.fusion.utils import clamp
from engine.fusion.logger import logger, measure_latency


class EvidenceScorer:
  """Normalizes and reliability-weights domain scores."""

  @measure_latency("normalize_and_score")
  def normalize_and_score(
      self,
      domain_map: Dict[str, WeightedEvidenceItem]
  ) -> Dict[str, WeightedEvidenceItem]:
    """Normalize raw scores to [0, 1], combine with reliability, and assign rule-based reasons."""
    for domain, item in domain_map.items():
      if item.status in (EvidenceStatus.UNAVAILABLE, EvidenceStatus.FAILED) or item.effective_weight <= 0.0:
        item.normalized_score = 0.0
        item.effective_score = 0.0
        item.reasons = [f"{domain.capitalize()} signal currently unavailable or off."]
        continue

      # Clamp raw score to [0, 1]
      norm = clamp(item.raw_score, 0.0, 1.0)
      rel = clamp(item.reliability, 0.0, 1.0)
      item.normalized_score = norm

      # Effective score blends normalized score with reliability (so low reliability softens the impact)
      item.effective_score = norm * (0.5 + 0.5 * rel)

      # Generate rule-based reason justification
      reasons: List[str] = []
      if domain == DOMAIN_IDENTITY:
        if norm >= 0.85:
          reasons.append(f"Strong identity metadata match (score: {norm:.2f}, rel: {rel:.2f})")
        elif norm >= 0.50:
          reasons.append(f"Moderate identity metadata match (score: {norm:.2f})")
        else:
          reasons.append(f"Weak identity match (score: {norm:.2f})")
      elif domain == DOMAIN_VISUAL:
        if norm >= 0.85:
          reasons.append(f"High facial recognition similarity (score: {norm:.2f}, rel: {rel:.2f})")
        elif norm >= 0.50:
          reasons.append(f"Moderate facial similarity (score: {norm:.2f})")
        else:
          reasons.append(f"Low facial similarity (score: {norm:.2f})")
      elif domain == DOMAIN_VOICE:
        if norm >= 0.85:
          reasons.append(f"High speaker voice acoustic similarity (score: {norm:.2f})")
        elif norm >= 0.50:
          reasons.append(f"Moderate voice similarity (score: {norm:.2f})")
        else:
          reasons.append(f"Low voice similarity (score: {norm:.2f})")
      elif domain == DOMAIN_BEHAVIOR:
        if norm >= 0.75:
          reasons.append(f"High behavioral engagement ratio (score: {norm:.2f})")
        else:
          reasons.append(f"Moderate/Low behavioral activity (score: {norm:.2f})")
      elif domain == DOMAIN_CONVERSATION:
        if norm >= 0.85:
          reasons.append(f"Strong candidate reasoning patterns / answered questions (score: {norm:.2f})")
        elif norm >= 0.50:
          reasons.append(f"Active interview conversation participation (score: {norm:.2f})")
        else:
          reasons.append(f"Limited candidate conversation evidence (score: {norm:.2f})")
      else:
        reasons.append(f"{domain.capitalize()} score evaluated at {norm:.2f}")

      if item.status == EvidenceStatus.STALE:
        reasons.append(f"Note: {domain.capitalize()} signal is stale ({item.age_seconds:.1f}s old)")

      item.reasons = reasons

    return domain_map


evidence_scorer = EvidenceScorer()
