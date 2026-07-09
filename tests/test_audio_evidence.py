import pytest
from engine.audio.evidence_provider import VoiceEvidenceProvider
from engine.audio.schemas import (
    VoiceEvidence,
    SpeechSegment,
    DiarizedSegment,
    SpeakerRecognitionResult,
    TranscriptSegment,
    LanguageDetectionResult
)

def test_evidence_provider_assembly():
  """Test that VoiceEvidenceProvider correctly aggregates individual outputs into one VoiceEvidence object."""
  speech = SpeechSegment(start=0.0, end=1.5, confidence=0.98)
  diarization = DiarizedSegment(speaker_label="SPEAKER_00", start=0.0, end=1.5, confidence=0.90)
  recognition = SpeakerRecognitionResult(
      speaker_label="SPEAKER_00",
      embedding=[0.1] * 192,
      similarity=0.88,
      matched_speaker_id="speaker_alice",
      confidence=1.0
  )
  transcript = TranscriptSegment(speaker_id="speaker_alice", text="Hello world", start=0.0, end=1.5)
  lang_detect = LanguageDetectionResult(language="en", confidence=0.95)

  evidence = VoiceEvidenceProvider.assemble_evidence(
      meeting_id="test_meeting_id",
      speech=speech,
      diarization=diarization,
      recognition=recognition,
      transcript=transcript,
      lang_detect=lang_detect
  )

  assert isinstance(evidence, VoiceEvidence)
  assert evidence.meeting_id == "test_meeting_id"
  assert evidence.speaker_id == "speaker_alice"
  assert evidence.voice_embedding == [0.1] * 192
  assert evidence.speaker_similarity == 0.88
  assert evidence.transcript == "Hello world"
  assert evidence.language == "en"
  assert evidence.speech_start == 0.0
  assert evidence.speech_end == 1.5
  assert evidence.speech_duration == 1.5
  assert evidence.speech_confidence == 0.98
  assert evidence.recognition_confidence == 1.0
  assert evidence.timestamp > 0
