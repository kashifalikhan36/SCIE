import pytest
import wave
import io
import struct
from engine.audio.whisper_transcriber import WhisperTranscriber
from engine.audio.schemas import DiarizedSegment, TranscriptSegment
from engine.audio.config import audio_config

def create_valid_wav_bytes(duration_sec: float = 1.0) -> bytes:
  """Creates a minimal valid mono PCM 16kHz WAV file in-memory."""
  wav_buffer = io.BytesIO()
  with wave.open(wav_buffer, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2) # 16-bit
    wav.setframerate(16000)
    # Write silent samples
    num_samples = int(16000 * duration_sec)
    samples = struct.pack(f"<{num_samples}h", *([0] * num_samples))
    wav.writeframesraw(samples)
  return wav_buffer.getvalue()

@pytest.mark.asyncio
async def test_whisper_transcriber():
  """Test that WhisperTranscriber transcribes audio using Groq API or mock fallbacks."""
  transcriber = WhisperTranscriber()
  
  segment = DiarizedSegment(speaker_label="SPEAKER_00", start=1.5, end=3.5, confidence=0.9)
  
  # Generate valid WAV audio bytes
  audio_bytes = create_valid_wav_bytes(duration_sec=2.0)
  
  # 1. Normal execution
  res = await transcriber.transcribe(audio_bytes, segment, "speaker_123")
  assert isinstance(res, TranscriptSegment)
  assert res.speaker_id == "speaker_123"
  assert res.start == 1.5
  assert res.end == 3.5
  
  # If real Groq API is active, res.text is either transcribed string or empty (for silence).
  # If mock fallback is active, it contains the mock timestamp text.
  if transcriber.client is None:
    assert "[Speech at" in res.text

  # 2. Empty input
  res_empty = await transcriber.transcribe(b"", segment, "speaker_123")
  assert res_empty.text == ""
