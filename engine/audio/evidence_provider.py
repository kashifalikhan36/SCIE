import time
import logging
from engine.audio.schemas import (
    VoiceEvidence,
    SpeechSegment,
    DiarizedSegment,
    SpeakerRecognitionResult,
    TranscriptSegment,
    LanguageDetectionResult
)

logger = logging.getLogger("SCIE.audio_engine.evidence_provider")

class VoiceEvidenceProvider:
  """Aggregates intermediate pipeline results into a unified VoiceEvidence artifact."""

  @staticmethod
  def assemble_evidence(
      meeting_id: str,
      speech: SpeechSegment,
      diarization: DiarizedSegment,
      recognition: SpeakerRecognitionResult,
      transcript: TranscriptSegment,
      lang_detect: LanguageDetectionResult
  ) -> VoiceEvidence:
    """Assembles all database and inference outputs into a structured VoiceEvidence instance."""
    
    duration = diarization.end - diarization.start
    
    evidence = VoiceEvidence(
        meeting_id=meeting_id,
        speaker_id=recognition.matched_speaker_id,
        voice_embedding=recognition.embedding,
        speaker_similarity=recognition.similarity,
        transcript=transcript.text,
        language=lang_detect.language,
        speech_start=diarization.start,
        speech_end=diarization.end,
        speech_duration=duration,
        speech_confidence=speech.confidence,
        recognition_confidence=recognition.confidence,
        timestamp=int(time.time() * 1000)
    )

    logger.info(
        f"Assembled VoiceEvidence for meeting {meeting_id}, speaker {recognition.matched_speaker_id}: "
        f"Duration: {duration:.2f}s, Similarity: {recognition.similarity:.2f}, Language: {lang_detect.language}"
    )
    return evidence
