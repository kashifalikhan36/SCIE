import pytest
from engine.audio.diarization import SpeakerDiarizer
from engine.audio.schemas import SpeechSegment, DiarizedSegment

@pytest.mark.asyncio
async def test_diarization_no_speech():
  """Test that Diarization returns empty list when speech segments list is empty."""
  diarizer = SpeakerDiarizer()
  res = await diarizer.diarize(b"\x01\x02", [])
  assert res == []

@pytest.mark.asyncio
async def test_diarization_mapping():
  """Test that Diarization correctly maps speech segments to speaker labels."""
  diarizer = SpeakerDiarizer()
  speech_segs = [
      SpeechSegment(start=0.0, end=0.5, confidence=0.9),
      SpeechSegment(start=0.5, end=1.0, confidence=0.8)
  ]
  
  res = await diarizer.diarize(b"\x01\x02" * 1000, speech_segs)
  assert len(res) == 2
  for segment in res:
    assert isinstance(segment, DiarizedSegment)
    assert segment.speaker_label == "SPEAKER_00"
    assert segment.confidence > 0.0
