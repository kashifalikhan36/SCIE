"""
Explanation Builder for the Evidence Fusion Engine (`engine/fusion/`).

Generates structured, rule-based explanations describing why a participant received
their confidence score, rank, and domain evaluation. Does NOT use GPT or LLM reasoning;
produces pure structured data ready for dashboard display or downstream natural language rendering.
"""
from typing import Dict, List
from engine.fusion.schemas import ParticipantState, ParticipantScore, Explanation
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.constants import (
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT,
    EvidenceStatus
)
from engine.fusion.utils import generate_explanation_id, now_ms
from engine.fusion.logger import logger, measure_latency


class ExplanationBuilder:
  """Builds structured, rule-based explanations for participant ranking and scores."""

  @measure_latency("build_explanation")
  def build_explanation(
      self,
      state: ParticipantState,
      score: ParticipantScore,
      domain_map: Dict[str, WeightedEvidenceItem]
  ) -> Explanation:
    """Generate a structured Explanation object based on domain scores and availability."""
    reasons_by_domain: Dict[str, List[str]] = {}
    summary_points: List[str] = []
    strengths: List[str] = []
    gaps: List[str] = []

    # 1. Analyze individual domains
    for domain, item in domain_map.items():
      if item.status in (EvidenceStatus.UNAVAILABLE, EvidenceStatus.FAILED) or item.effective_weight <= 0.01:
        gaps.append(f"{domain.capitalize()} signal currently unavailable or off.")
        reasons_by_domain[domain] = [f"{domain.capitalize()} evidence unavailable."]
        continue

      domain_reasons = list(item.reasons)
      reasons_by_domain[domain] = domain_reasons

      # Categorize as strength or gap
      if item.normalized_score >= 0.80 and item.reliability >= 0.70:
        if domain == DOMAIN_VISUAL:
          strengths.append(f"Highest visual face similarity ({item.normalized_score:.2f})")
        elif domain == DOMAIN_VOICE:
          strengths.append(f"Strong voice similarity ({item.normalized_score:.2f})")
        elif domain == DOMAIN_CONVERSATION:
          strengths.append("Answered most interview questions and demonstrated domain reasoning")
        elif domain == DOMAIN_IDENTITY:
          strengths.append(f"Strong metadata match on display name or email ({item.normalized_score:.2f})")
        elif domain == DOMAIN_BEHAVIOR:
          strengths.append("Consistent camera usage and active behavioral engagement")
        else:
          strengths.append(f"Strong {domain} signal ({item.normalized_score:.2f})")
      elif item.normalized_score <= 0.35:
        gaps.append(f"Low evaluation score on {domain} ({item.normalized_score:.2f})")

      if item.status == EvidenceStatus.STALE:
        gaps.append(f"{domain.capitalize()} signal has not updated recently ({item.age_seconds:.0f}s old)")

    # 2. Build summary points
    rank_str = f"Rank {score.rank}"
    summary_points.append(
        f"Participant evaluated at {rank_str} with {score.confidence * 100:.1f}% overall confidence "
        f"and {score.final_score * 100:.1f}% weighted score."
    )

    if strengths:
      summary_points.append(f"Key corroborating signals: {', '.join(strengths[:3])}.")
    if gaps:
      summary_points.append(f"Noted gaps/unavailable signals: {', '.join(gaps[:2])}.")

    logger.debug(f"ExplanationBuilder: Built explanation for participant={state.participant_id} (rank={score.rank}).")
    return Explanation(
        explanation_id=generate_explanation_id(),
        meeting_id=state.meeting_id,
        participant_id=state.participant_id,
        summary_points=summary_points,
        reasons_by_domain=reasons_by_domain,
        key_strengths=strengths,
        key_gaps=gaps,
        timestamp=now_ms()
    )


explanation_builder = ExplanationBuilder()
