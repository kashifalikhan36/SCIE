from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class AudioChunk(BaseModel):
  meeting_id: str
  timestamp: int
  chunk_index: int
  data: bytes
  file_path: Optional[str] = None
  chunk_type: str = "audio"  # "audio" (tab) or "mic_audio" (mic)

class SpeechSegment(BaseModel):
  start: float = Field(..., description="Speech start time in seconds from window start")
  end: float = Field(..., description="Speech end time in seconds from window start")
  confidence: float = Field(..., description="Confidence score of speech detection")

class DiarizedSegment(BaseModel):
  speaker_label: str = Field(..., description="Diarized speaker label, e.g., SPEAKER_00")
  start: float
  end: float
  confidence: float

class SpeakerRecognitionResult(BaseModel):
  speaker_label: str
  embedding: List[float] = Field(..., description="Generated speaker embedding vector")
  similarity: float = Field(..., description="Similarity score against best-match previous speaker")
  matched_speaker_id: str = Field(..., description="Identified speaker_id or new label if unmatched")
  confidence: float

class TranscriptSegment(BaseModel):
  speaker_id: str
  text: str
  start: float
  end: float
  is_final: bool = True

class LanguageDetectionResult(BaseModel):
  language: str = Field(..., description="Detected language code, e.g., 'en', 'es'")
  confidence: float

class VoiceEvidence(BaseModel):
  meeting_id: str
  speaker_id: str
  voice_embedding: List[float]
  speaker_similarity: float
  transcript: str
  language: str
  speech_start: float
  speech_end: float
  speech_duration: float
  speech_confidence: float
  recognition_confidence: float
  timestamp: int = Field(..., description="Epoch timestamp of generation")

class ParticipantAudioState(BaseModel):
  speaker_id: str
  voice_embedding: List[float]
  last_transcript: str
  language: str
  last_seen: int
  speech_duration: float
  speech_segments: List[Dict[str, Any]] = Field(default_factory=list)
  recognition_score: float
  last_updated: int
