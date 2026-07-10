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

  def _transcribe_sync(self, audio_data: bytes) -> str:
    """Synchronous: decode WebM → WAV via ffmpeg, write to temp file, call Azure recognize_once.
    
    audio_data may be either:
    - A single concatenated blob of raw bytes from the pipeline window (legacy path)
    - A single self-contained WebM file (used by direct calls / tests)
    
    In either case we attempt to decode it. For multi-chunk windows the pipeline
    should call _transcribe_sync_chunks() directly.
    """
    import imageio_ffmpeg, tempfile, os, wave
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    # Decode the WebM → raw PCM
    raw_pcm = self._decode_webm_to_pcm(audio_data, ffmpeg_exe)

    if not raw_pcm:
      raise ValueError("FFmpeg failed to extract PCM from WebM bytes — audio may not be valid WebM.")

    logger.info(f"[Single] Extracted {len(raw_pcm)} PCM bytes from WebM.")
    return self._recognize_from_pcm(raw_pcm)

  def _transcribe_sync_chunks(self, chunk_data_list: list) -> str:
    """Decode each WebM chunk individually and concatenate PCM before recognizing.
    
    This is the correct path for multi-chunk windows. Each chunk from the browser
    extension is a self-contained valid WebM file (EBML header + clusters). Naively
    concatenating the raw bytes produces invalid multi-header WebM. Instead we decode
    each chunk separately and stitch the raw PCM together.
    """
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    all_pcm = b""
    for i, chunk_bytes in enumerate(chunk_data_list):
      pcm = self._decode_webm_to_pcm(chunk_bytes, ffmpeg_exe)
      if pcm:
        all_pcm += pcm
        logger.info(f"  Chunk {i}: {len(chunk_bytes)} WebM → {len(pcm)} PCM")
      else:
        logger.warning(f"  Chunk {i}: {len(chunk_bytes)} WebM → 0 PCM (decode failed)")

    if not all_pcm:
      raise ValueError("No PCM could be extracted from any chunk in this window.")

    duration_sec = len(all_pcm) / (16000 * 2)  # 16kHz, 16-bit
    logger.info(f"[Chunks] Total PCM: {len(all_pcm)} bytes ({duration_sec:.1f}s) from {len(chunk_data_list)} chunks.")

    # DEBUG: Save a diagnostic WAV to disk so we can verify audio content
    try:
      import wave, os
      diag_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'debug_audio.wav')
      diag_path = os.path.abspath(diag_path)
      with wave.open(diag_path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(all_pcm)
      logger.info(f"[DEBUG] Saved diagnostic WAV: {diag_path}")
    except Exception as e:
      logger.warning(f"Failed to save diagnostic WAV: {e}")

    return self._recognize_from_pcm(all_pcm)

  def _recognize_from_pcm(self, raw_pcm: bytes) -> str:
    """Write PCM to a temp WAV file and run Azure Speech recognize_once."""
    import imageio_ffmpeg, tempfile, os, wave
    
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
      matched_speaker_id: str,
      chunk_data_list: list = None   # individual WebM chunk bytes; preferred for pipeline windows
  ) -> TranscriptSegment:
    """Sends audio to Azure Speech and returns a structured TranscriptSegment.
    
    When chunk_data_list is provided, each chunk is decoded from WebM independently
    before PCM is stitched together. This avoids the multi-EBML-header problem that
    occurs when raw WebM bytes are naively concatenated.
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
        logger.info(f"Sending audio to Azure Speech ({len(chunk_data_list or [])} chunks / {len(audio_data)} raw bytes)...")
        
        # Prefer per-chunk decode path when chunk list is available
        if chunk_data_list:
          text = await asyncio.to_thread(self._transcribe_sync_chunks, chunk_data_list)
        else:
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
