import logging
import asyncio
import subprocess
from typing import List, Optional
import azure.cognitiveservices.speech as speechsdk

from engine.audio.config import audio_config
from engine.audio.schemas import DiarizedSegment, TranscriptSegment

logger = logging.getLogger("SCIE.audio_engine.azure_transcriber")

class WhisperTranscriber:
  """Transcribes audio chunks using Azure Cognitive Services Speech SDK (Class kept named WhisperTranscriber for compatibility)."""

  def __init__(self):
    self.api_key = audio_config.AZURE_OPENAI_API_KEY
    self.endpoint = audio_config.AZURE_OPENAI_ENDPOINT
    
    if self.api_key and self.endpoint:
      self.speech_config = speechsdk.SpeechConfig(
          subscription=self.api_key,
          endpoint=self.endpoint
      )
      self.is_configured = True
    else:
      self.is_configured = False
      logger.warning("Azure Speech keys not configured. Transcriber will use mock transcription.")

  def _decode_webm_to_pcm(self, webm_data: bytes, ffmpeg_exe: str) -> bytes:
    """Decode a single self-contained WebM chunk to 16kHz 16-bit mono PCM via ffmpeg."""
    process = subprocess.Popen(
        [ffmpeg_exe, '-f', 'webm', '-i', 'pipe:0',
         '-f', 's16le', '-ac', '1', '-ar', '16000', 'pipe:1'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    pcm, _ = process.communicate(input=webm_data)
    return pcm

  def _transcribe_sync(self, raw_pcm: bytes) -> str:
    """Write PCM to a temp WAV file and run Azure Speech recognize_once."""
    import tempfile, os, wave
    
    # DEBUG: Save a diagnostic WAV to disk so we can verify audio content
    try:
      diag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'debug_audio.wav')
      diag_path = os.path.abspath(diag_path)
      with wave.open(diag_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(raw_pcm)
      logger.info(f"[DEBUG] Saved diagnostic WAV: {diag_path}")
    except Exception as e:
      logger.warning(f"Failed to save diagnostic WAV: {e}")

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
      tmp_path = tmp.name
      with wave.open(tmp_path, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)   # 16-bit = 2 bytes
        wav_file.setframerate(16000)
        wav_file.writeframes(raw_pcm)

    try:
      audio_cfg = speechsdk.audio.AudioConfig(filename=tmp_path)
      recognizer = speechsdk.SpeechRecognizer(
          speech_config=self.speech_config,
          audio_config=audio_cfg
      )
      result = recognizer.recognize_once()

      if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        logger.info(f"Azure Speech RECOGNIZED: '{result.text.strip()}'")
        return result.text.strip()
      elif result.reason == speechsdk.ResultReason.NoMatch:
        no_match_detail = result.no_match_details
        logger.warning(f"Azure Speech NoMatch — reason: {no_match_detail.reason}")
        return ""
      elif result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        logger.error(f"Azure Speech canceled: {details.reason} — {details.error_details}")
        raise Exception(f"Azure Speech Error: {details.error_details}")
      return ""
    finally:
      try:
        os.unlink(tmp_path)
      except Exception:
        pass

  async def transcribe(
      self,
      audio_data: bytes,
      segment: DiarizedSegment,
      matched_speaker_id: str
  ) -> TranscriptSegment:
    """Sends audio to Azure Speech and returns a structured TranscriptSegment.
    
    audio_data should be valid PCM data.
    """
    if not audio_data or len(audio_data) == 0:
      return TranscriptSegment(
          speaker_id=matched_speaker_id,
          text="",
          start=segment.start,
          end=segment.end,
          is_final=True
      )

    # Use real Azure API if configured
    if self.is_configured:
      try:
        logger.info(f"Sending audio to Azure Speech ({len(audio_data)} raw PCM bytes)...")
        
        text = await asyncio.to_thread(self._transcribe_sync, audio_data)
        
        logger.info(f"Received Azure transcription: '{text}'")
        
        return TranscriptSegment(
            speaker_id=matched_speaker_id,
            text=text,
            start=segment.start,
            end=segment.end,
            is_final=True
        )
      except Exception as e:
        logger.error(f"Azure Speech transcription failed: {e}. Falling back to mock transcription.")

    # Fallback/Mock: Return dummy text indicating speech was processed
    mock_text = f"[Speech at {segment.start:.2f}s - {segment.end:.2f}s]"
    logger.info(f"Azure (Mock): Generated placeholder text: '{mock_text}'")
    
    return TranscriptSegment(
        speaker_id=matched_speaker_id,
        text=mock_text,
        start=segment.start,
        end=segment.end,
        is_final=True
    )
