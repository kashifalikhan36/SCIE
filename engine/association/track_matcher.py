import logging
from typing import Optional, List

from engine.association.schemas import TrackMatchEvidence
from engine.video.schemas import VisualEvidence
from engine.association.exceptions import TrackMatcherError

logger = logging.getLogger("SCIE.association_engine.track_matcher")


class TrackMatcher:
  """Associates Track IDs with Participant IDs using visual embedding similarity,
  face tracking confidence, and visibility state.
  """

  def match(
      self,
      target_track_id: Optional[str],
      visual_evidence: VisualEvidence,
  ) -> TrackMatchEvidence:
    """Evaluates whether incoming VisualEvidence matches target participant profile."""
    try:
      reasons: List[str] = []
      score = 0.0
      confidence = 0.0

      if not target_track_id:
        return TrackMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=["No target track ID assigned yet for correlation."],
            track_id=visual_evidence.track_id,
            visual_similarity=visual_evidence.face_similarity,
            visibility=visual_evidence.visibility
        )

      # Exact ID match check
      if target_track_id == visual_evidence.track_id:
        if visual_evidence.visibility:
          score = max(0.85, visual_evidence.face_similarity)
          confidence = visual_evidence.tracking_confidence
          reasons.append(
              f"Exact track_id match '{target_track_id}' "
              f"(visible, sim: {visual_evidence.face_similarity:.2f}, track_conf: {visual_evidence.tracking_confidence:.2f})"
          )
        else:
          # Track exists but currently occluded / camera off
          score = max(0.60, visual_evidence.face_similarity * 0.80)
          confidence = visual_evidence.tracking_confidence * 0.70
          reasons.append(
              f"Exact track_id match '{target_track_id}' currently hidden/camera off "
              f"(last sim: {visual_evidence.face_similarity:.2f})"
          )
      else:
        # High face embedding similarity despite ID change (e.g., re-joined or tracker re-ID)
        if visual_evidence.face_similarity >= 0.88 and visual_evidence.visibility:
          score = visual_evidence.face_similarity
          confidence = visual_evidence.recognition_confidence * 0.85
          reasons.append(
              f"High face embedding similarity ({visual_evidence.face_similarity:.2f}) "
              f"with track '{visual_evidence.track_id}' despite ID mismatch."
          )
        else:
          score = 0.0
          confidence = 0.0
          reasons.append(
              f"Track ID mismatch ('{visual_evidence.track_id}' != target '{target_track_id}') "
              f"and low face similarity ({visual_evidence.face_similarity:.2f})."
          )

      logger.debug(
          f"TrackMatcher: target={target_track_id}, incoming={visual_evidence.track_id}, "
          f"score={score:.2f}, conf={confidence:.2f}, visible={visual_evidence.visibility}"
      )
      return TrackMatchEvidence(
          score=round(score, 4),
          confidence=round(confidence, 4),
          reasons=reasons,
          track_id=visual_evidence.track_id,
          visual_similarity=round(visual_evidence.face_similarity, 4),
          visibility=visual_evidence.visibility
      )

    except Exception as exc:
      raise TrackMatcherError(f"Failed to execute TrackMatcher: {exc}") from exc
