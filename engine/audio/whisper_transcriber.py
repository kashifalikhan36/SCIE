import io
import logging
from typing import List, Optional
from groq import AsyncGroq
from engine.audio.config import audio_config
from engine.audio.schemas import DiarizedSegment, TranscriptSegment
from engine.audio.exceptions import TranscriberError

logger = logging.getLogger("SCIE.audio_engine.whisper_transcriber")

class WhisperTranscriber:
  """Transcribes audio chunks using the Whisper Large v3 model via the Groq API."""

  def __init__(self):
    self.api_key = audio_config.GROQ_API_KEY
    if self.api_key:
      self.client = AsyncGroq(api_key=self.api_key)
    else:
      self.client = None
      logger.warning("GROQ_API_KEY is not configured in settings. WhisperTranscriber will use mock transcription.")

  async def transcribe(self, audio_data: bytes, segment: DiarizedSegment, matched_speaker_id: str) -> TranscriptSegment:
    """Sends the speech audio chunk to Groq's Whisper API and returns a structured TranscriptSegment."""
    if not audio_data or len(audio_data) == 0:
      return TranscriptSegment(
          speaker_id=matched_speaker_id,
          text="",
          start=segment.start,
          end=segment.end,
          is_final=True
      )

    # Use real Groq API if key is present
    if self.client is not None:
      try:
        # Wrap audio bytes into a memory buffer formatted for Groq audio transcription
        audio_buffer = io.BytesIO(audio_data)
        audio_buffer.name = "audio.webm" # Groq expects a filename to detect mime type
        
        logger.info(f"Sending audio segment to Groq Whisper model (size: {len(audio_data)} bytes)...")
        
        # Call Groq audio transcription endpoint
        response = await self.client.audio.transcriptions.create(
            file=audio_buffer,
            model=audio_config.GROQ_AUDIO_MODEL,
            response_format="verbose_json"
        )
        
        text = response.text.strip() if hasattr(response, "text") else ""
        logger.info(f"Received Whisper transcription: '{text}'")
        
        return TranscriptSegment(
            speaker_id=matched_speaker_id,
            text=text,
            start=segment.start,
            end=segment.end,
            is_final=True
        )
      except Exception as e:
        logger.error(f"Groq Whisper transcription API call failed: {e}. Falling back to mock transcription.")

    # Fallback/Mock: Return dummy text indicating speech was processed
    mock_text = f"[Speech at {segment.start:.2f}s - {segment.end:.2f}s]"
    logger.info(f"Whisper (Mock): Generated placeholder text: '{mock_text}'")
    
    return TranscriptSegment(
        speaker_id=matched_speaker_id,
        text=mock_text,
        start=segment.start,
        end=segment.end,
        is_final=True
    )
