import pytest
from engine.audio.whisper_transcriber import WhisperTranscriber
from engine.audio.schemas import DiarizedSegment, TranscriptSegment

@pytest.mark.asyncio
async def test_whisper_transcriber():
  """Test that WhisperTranscriber transcribes audio to segments correctly (using mock fallbacks)."""
  transcriber = WhisperTranscriber()
  
  segment = DiarizedSegment(speaker_label="SPEAKER_00", start=1.5, end=3.5, confidence=0.9)
  
  # 1. Normal execution
  res = await transcriber.transcribe(b"\x01\x02" * 1000, segment, "speaker_123")
  assert isinstance(res, TranscriptSegment)
  assert res.speaker_id == "speaker_123"
  assert "1.50" in res.text or "[Speech at" in res.text
  assert res.start == 1.5
  assert res.end == 3.5
  
  # 2. Empty input
  res_empty = await transcriber.transcribe(b"", segment, "speaker_123")
  assert res_empty.text == ""
