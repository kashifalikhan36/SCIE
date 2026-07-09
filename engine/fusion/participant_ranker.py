"""
Participant Ranker for the Evidence Fusion Engine (`engine/fusion/`).

Evaluates all active participants across the meeting, computes weighted final scores,
sorts participants by confidence and score, and assigns sequential ranks (`1, 2, ...`).
Returns the complete ranking breakdown for all participants.
"""
from typing import Dict, List
from engine.fusion.schemas import ParticipantState, ParticipantScore, RankingResult
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.utils import clamp, now_ms
from engine.fusion.logger import logger, measure_latency


class ParticipantRanker:
  """Sorts and ranks all meeting participants based on multi-signal fusion scores."""

  @measure_latency("rank_participants")
  def rank_participants(
      self,
      meeting_id: str,
      states: Dict[str, ParticipantState],
      domain_maps: Dict[str, Dict[str, WeightedEvidenceItem]]
  ) -> RankingResult:
    """Evaluate and rank all participants in a meeting.

    Args:
      meeting_id: Meeting ID being evaluated.
      states: Mapping of participant_id -> ParticipantState.
      domain_maps: Mapping of participant_id -> { domain -> WeightedEvidenceItem }.

    Returns:
      RankingResult with sequential ranks assigned across all participants.
    """
    scores_list: List[ParticipantScore] = []

    for pid, state in states.items():
      dmap = domain_maps.get(pid, {})
      breakdown: Dict[str, float] = {}
      total_weighted_score = 0.0
      all_reasons: List[str] = list(state.reasons)

      for domain, item in dmap.items():
        breakdown[domain] = round(item.normalized_score, 4)
        total_weighted_score += item.effective_score
        # Add high-priority reasons if not already present
        for r in item.reasons:
          if r not in all_reasons and not r.startswith("Note:"):
            all_reasons.append(r)

      final_score = clamp(total_weighted_score, 0.0, 1.0)

      score_obj = ParticipantScore(
          participant_id=pid,
          final_score=round(final_score, 4),
          confidence=round(state.confidence, 4),
          rank=0,  # Will be assigned after sorting
          reasons=all_reasons[:8],
          evidence_breakdown=breakdown
      )
      scores_list.append(score_obj)

    # Sort primarily by confidence-weighted score, secondary by confidence, tertiary by final_score
    scores_list.sort(
        key=lambda s: (s.confidence * s.final_score, s.confidence, s.final_score),
        reverse=True
    )

    # Assign sequential rank starting from 1
    for idx, score_obj in enumerate(scores_list, start=1):
      score_obj.rank = idx

    logger.debug(f"ParticipantRanker: Ranked {len(scores_list)} participants for meeting={meeting_id}.")
    return RankingResult(
        meeting_id=meeting_id,
        ranking=scores_list,
        timestamp=now_ms()
    )


participant_ranker = ParticipantRanker()
