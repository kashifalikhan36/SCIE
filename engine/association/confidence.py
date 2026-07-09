import logging
from typing import List, Tuple, Optional

from engine.association.schemas import (
    MetadataMatchEvidence,
    TranscriptMatchEvidence,
    SpeakerMatchEvidence,
    TrackMatchEvidence,
    TimelineMatchEvidence,
)
from engine.association.config import association_config
from engine.association.exceptions import ConfidenceCalculationError

logger = logging.getLogger("SCIE.association_engine.confidence")


class ConfidenceCalculator:
  """Synthesizes normalized scores, confidence estimates, and explanation reasons
  from all five matchers into a single unified association score and confidence.

  Uses configurable weights (WEIGHT_METADATA, WEIGHT_TIMELINE, WEIGHT_SPEAKER,
  WEIGHT_TRANSCRIPT, WEIGHT_TRACK) from association_config.
  """

  def calculate(
      self,
      metadata_evidence: Optional[MetadataMatchEvidence] = None,
      transcript_evidence: Optional[TranscriptMatchEvidence] = None,
      speaker_evidence: Optional[SpeakerMatchEvidence] = None,
      track_evidence: Optional[TrackMatchEvidence] = None,
      timeline_evidence: Optional[TimelineMatchEvidence] = None,
  ) -> Tuple[float, float, List[str]]:
    """Calculates overall (association_score, association_confidence, aggregated_reasons).

    Only weights evidences that are active/provided for the current evaluation pass,
    dynamically normalizing weights so partial signal updates do not artificially penalize
    association confidence.
    """
    try:
      total_score_weighted = 0.0
      total_conf_weighted = 0.0
      active_weight_sum = 0.0
      aggregated_reasons: List[str] = []

      # Helper for accumulating weighted evidence
      def _accumulate(evidence: Any, weight: float, label: str):
        nonlocal total_score_weighted, total_conf_weighted, active_weight_sum, aggregated_reasons
        if evidence is not None and (evidence.score > 0.0 or evidence.confidence > 0.0 or evidence.reasons):
          total_score_weighted += evidence.score * weight
          total_conf_weighted += evidence.confidence * weight
          active_weight_sum += weight
          for r in evidence.reasons:
            if r and r not in aggregated_reasons:
              aggregated_reasons.append(f"[{label}] {r}")

      _accumulate(metadata_evidence, association_config.WEIGHT_METADATA, "Metadata")
      _accumulate(timeline_evidence, association_config.WEIGHT_TIMELINE, "Timeline")
      _accumulate(speaker_evidence, association_config.WEIGHT_SPEAKER, "Speaker")
      _accumulate(transcript_evidence, association_config.WEIGHT_TRANSCRIPT, "Transcript")
      _accumulate(track_evidence, association_config.WEIGHT_TRACK, "Track")

      if active_weight_sum <= 0.0:
        return 0.0, 0.0, ["No active evidence signals contributed to confidence calculation."]

      # Normalize by active weight sum so score/confidence stay bounded between 0.0 and 1.0
      norm_score = min(1.0, total_score_weighted / active_weight_sum)
      norm_conf = min(1.0, total_conf_weighted / active_weight_sum)

      # Boost confidence when multiple independent modalities align (e.g. metadata + track + speaker)
      modality_count = sum([
          1 for ev in [metadata_evidence, timeline_evidence, speaker_evidence, transcript_evidence, track_evidence]
          if ev is not None and (ev.confidence >= 0.50 or ev.score >= 0.50)
      ])
      if modality_count >= 3:
        norm_conf = min(1.0, norm_conf * 1.15)
        norm_score = min(1.0, norm_score * 1.10)
      elif modality_count == 2:
        norm_conf = min(1.0, norm_conf * 1.05)

      logger.debug(
          f"ConfidenceCalculator: score={norm_score:.4f}, conf={norm_conf:.4f}, "
          f"active_weight_sum={active_weight_sum:.2f}, modalities={modality_count}"
      )
      return round(norm_score, 4), round(norm_conf, 4), aggregated_reasons

    except Exception as exc:
      raise ConfidenceCalculationError(f"Failed to calculate association confidence: {exc}") from exc
