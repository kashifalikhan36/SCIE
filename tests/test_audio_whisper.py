import pytest
import wave
import io
import struct
import subprocess
import imageio_ffmpeg
from engine.audio.whisper_transcriber import WhisperTranscriber
from engine.audio.schemas import DiarizedSegment, TranscriptSegment
from engine.audio.config import audio_config

def create_valid_webm_bytes(duration_sec: float = 2.0) -> bytes:
  """Creates a minimal valid WebM/Opus audio file in-memory using ffmpeg (silence)."""
  ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
  # Generate silence as WebM/Opus, same format the browser extension sends
  process = subprocess.Popen(
      [ffmpeg_exe, '-f', 'lavfi', '-i', f'anullsrc=r=16000:cl=mono:d={duration_sec}',
       '-c:a', 'libopus', '-f', 'webm', 'pipe:1'],
      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
  )
  out, _ = process.communicate()
  return out

@pytest.mark.asyncio
async def test_whisper_transcriber():
  """Test that WhisperTranscriber transcribes audio using Azure Speech or mock fallback."""
  transcriber = WhisperTranscriber()
  
  segment = DiarizedSegment(speaker_label="SPEAKER_00", start=1.5, end=3.5, confidence=0.9)
  
  # Generate valid WebM audio bytes (silent)
  audio_bytes = create_valid_webm_bytes(duration_sec=2.0)
  assert len(audio_bytes) > 0, "FFmpeg failed to generate test WebM"
  
  # 1. Normal execution
  res = await transcriber.transcribe(audio_bytes, segment, "speaker_123")
  assert isinstance(res, TranscriptSegment)
  assert res.speaker_id == "speaker_123"
  assert res.start == 1.5
  assert res.end == 3.5
  
  # If Azure is not configured, mock fallback produces timestamp text.
  # If Azure is configured but silence → empty string (NoMatch).
  # Either way, res.text is a string.
  assert isinstance(res.text, str)
  if not transcriber.is_configured:
    assert "[Speech at" in res.text

  # 2. Empty input → always returns empty text
  res_empty = await transcriber.transcribe(b"", segment, "speaker_123")
  assert res_empty.text == ""

