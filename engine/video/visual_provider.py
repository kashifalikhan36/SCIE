import logging
from engine.video.schemas import (
    VisualEvidence,
    DetectedFace,
    DiarizedTrack
)

logger = logging.getLogger("SCIE.video_engine.visual_provider")

class VisualEvidenceProvider:
  """Aggregates intermediate video frame analysis stages into unified VisualEvidence objects."""

  @staticmethod
  def assemble_evidence(
      meeting_id: str,
      track: DiarizedTrack,
      face: DetectedFace,
      embedding: list,
      similarity: float,
      rec_confidence: float
  ) -> VisualEvidence:
    """Assembles all intermediate analysis data frames into a structured VisualEvidence schema instance."""
    
    evidence = VisualEvidence(
        meeting_id=meeting_id,
        track_id=track.track_id,
        frame_id=face.frame_id,
        face_embedding=embedding,
        face_similarity=similarity,
        recognition_confidence=rec_confidence,
        detection_confidence=face.confidence,
        tracking_confidence=track.confidence,
        visibility=track.visibility,
        timestamp=face.timestamp
    )

    logger.debug(
        f"Assembled VisualEvidence for meeting {meeting_id}, track {track.track_id}: "
        f"Frame: {face.frame_id}, Similarity: {similarity:.2f}, Visible: {track.visibility}"
    )
    return evidence
