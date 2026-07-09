import pytest
from engine.audio.vad import VoiceActivityDetector
from engine.audio.schemas import SpeechSegment

@pytest.mark.asyncio
async def test_vad_empty_audio():
  """Test that VAD returns empty list for empty audio input."""
  detector = VoiceActivityDetector()
  res = await detector.detect_speech(b"", 1.0)
  assert res == []
  
  res_none = await detector.detect_speech(None, 1.0)
  assert res_none == []

@pytest.mark.asyncio
async def test_vad_silence():
  """Test that VAD detects silence (low energy ratio) and skips window."""
  detector = VoiceActivityDetector()
  # Silent padding (all zeros)
  silent_bytes = b"\x00" * 32000
  res = await detector.detect_speech(silent_bytes, 1.0)
  assert res == []

@pytest.mark.asyncio
async def test_vad_speech():
  """Test that VAD detects speech when non-zero bytes are present."""
  detector = VoiceActivityDetector()
  # Bytes containing energy data
  speech_bytes = b"\x01\x02\x03\x04" * 8000
  res = await detector.detect_speech(speech_bytes, 1.0)
  assert len(res) == 1
  assert isinstance(res[0], SpeechSegment)
  assert res[0].start == 0.0
  assert res[0].end == 1.0
  assert res[0].confidence > 0.0
