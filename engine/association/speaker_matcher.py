import logging
from typing import Optional, List

from engine.association.schemas import SpeakerMatchEvidence
from engine.audio.schemas import VoiceEvidence
from engine.association.exceptions import SpeakerMatcherError

logger = logging.getLogger("SCIE.association_engine.speaker_matcher")


class SpeakerMatcher:
  """Associates Speaker IDs with Participant IDs using voice similarity,
  speech activity duration, and audio event cues.
  """

  def match(
      self,
      target_speaker_id: Optional[str],
      voice_evidence: VoiceEvidence,
  ) -> SpeakerMatchEvidence:
    """Evaluates whether incoming VoiceEvidence matches target participant profile."""
    try:
      reasons: List[str] = []
      score = 0.0
      confidence = 0.0

      if not target_speaker_id:
        return SpeakerMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=["No target speaker ID assigned yet for correlation."],
            speaker_id=voice_evidence.speaker_id,
            voice_similarity=voice_evidence.speaker_similarity
        )

      # Exact ID match check
      if target_speaker_id == voice_evidence.speaker_id:
        score = max(0.80, voice_evidence.speaker_similarity)
        # Factor in speech duration and model recognition confidence
        dur_boost = min(0.15, (voice_evidence.speech_duration / 60.0) * 0.05)
        confidence = min(1.0, voice_evidence.recognition_confidence + dur_boost)
        reasons.append(
            f"Exact speaker_id match '{target_speaker_id}' "
            f"(sim: {voice_evidence.speaker_similarity:.2f}, dur: {voice_evidence.speech_duration:.1f}s)"
        )
      else:
        # High voice embedding similarity despite different ID (e.g. re-diarized speaker)
        if voice_evidence.speaker_similarity >= 0.85:
          score = voice_evidence.speaker_similarity
          confidence = voice_evidence.recognition_confidence * 0.80
          reasons.append(
              f"High voice embedding similarity ({voice_evidence.speaker_similarity:.2f}) "
              f"with speaker '{voice_evidence.speaker_id}' despite ID mismatch."
          )
        else:
          score = 0.0
          confidence = 0.0
          reasons.append(
              f"Speaker ID mismatch ('{voice_evidence.speaker_id}' != target '{target_speaker_id}') "
              f"and low embedding similarity ({voice_evidence.speaker_similarity:.2f})."
          )

      logger.debug(
          f"SpeakerMatcher: target={target_speaker_id}, incoming={voice_evidence.speaker_id}, "
          f"score={score:.2f}, conf={confidence:.2f}"
      )
      return SpeakerMatchEvidence(
          score=round(score, 4),
          confidence=round(confidence, 4),
          reasons=reasons,
          speaker_id=voice_evidence.speaker_id,
          voice_similarity=round(voice_evidence.speaker_similarity, 4)
      )

    except Exception as exc:
      raise SpeakerMatcherError(f"Failed to execute SpeakerMatcher: {exc}") from exc
