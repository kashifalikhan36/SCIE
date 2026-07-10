"""
Transcription via Groq Whisper API.

Kept named WhisperTranscriber for drop-in compatibility with the audio pipeline.
Sends 16kHz mono WAV audio to Groq's whisper-large-v3 endpoint.
Falls back to a timestamped placeholder if GROQ_API_KEY is not set.
"""
import os
import logging
import asyncio
import wave
import tempfile
import subprocess
from typing import Optional

from engine.audio.config import audio_config
from engine.audio.schemas import DiarizedSegment, TranscriptSegment

logger = logging.getLogger("SCIE.audio_engine.groq_transcriber")

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


import asyncio

class WhisperTranscriber:
    """Transcribes diarized audio segments using Groq Whisper API."""

    def __init__(self):
        self._api_key = audio_config.GROQ_API_KEY
        self._model   = audio_config.GROQ_AUDIO_MODEL
        # Limit concurrency to 2 to prevent Groq 429 and Azure Speech connection limits
        self._semaphore = asyncio.Semaphore(2)
        
        if self._api_key:
            logger.info(f"GroqTranscriber: Using model '{self._model}' via Groq API.")
        else:
            logger.warning("GroqTranscriber: GROQ_API_KEY not set in .env — will use mock transcription.")

    def _pcm_to_wav_bytes(self, raw_pcm: bytes) -> bytes:
        """Convert raw 16kHz 16-bit mono PCM bytes to a WAV file in memory."""
        import io
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)       # mono
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(16000)   # 16kHz
            wf.writeframes(raw_pcm)
        return buf.getvalue()

    def _transcribe_sync(self, raw_pcm: bytes) -> str:
        """Write PCM to a temp WAV file and POST it to Groq's transcription endpoint.
        Falls back to Azure Speech if Groq is unconfigured or fails."""
        import requests

        wav_bytes = self._pcm_to_wav_bytes(raw_pcm)

        # Sanity check: if PCM is all zeros (silence), skip the API call
        if len(set(raw_pcm)) <= 2:
            logger.debug("GroqTranscriber: PCM appears to be silence — skipping API call.")
            return ""

        # 1. Try Groq Whisper First
        if self._api_key:
            try:
                logger.info(f"GroqTranscriber: Sending {len(wav_bytes):,} bytes WAV to Groq Whisper...")
                resp = requests.post(
                    GROQ_TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                    data={"model": self._model, "response_format": "json"},
                    timeout=60,
                )
                resp.raise_for_status()
                text = resp.json().get("text", "").strip()
                logger.info(f"GroqTranscriber: Received transcript ({len(text)} chars): '{text[:80]}...' " if len(text) > 80 else f"GroqTranscriber: Received: '{text}'")
                return text
            except Exception as e:
                logger.warning(f"GroqTranscriber: Groq API failed ({e}). Falling back to Azure Speech...")

        # 2. Fallback to Azure Speech SDK
        azure_api_key = audio_config.AZURE_OPENAI_API_KEY
        azure_endpoint = audio_config.AZURE_OPENAI_ENDPOINT
        
        if azure_api_key and azure_endpoint:
            try:
                import azure.cognitiveservices.speech as speechsdk
                
                # Convert standard OpenAI endpoint to Cognitive Services endpoint if needed
                endpoint_url = azure_endpoint.replace(".openai.azure.com", ".cognitiveservices.azure.com")
                
                logger.info(f"GroqTranscriber: Trying Azure Speech fallback with endpoint {endpoint_url}...")
                
                speech_config = speechsdk.SpeechConfig(
                    subscription=azure_api_key,
                    endpoint=endpoint_url
                )
                
                # Prevent NoMatch due to initial silence in long segments
                speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "30000")
                
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
                    tmp_wav.write(wav_bytes)
                    tmp_wav_path = tmp_wav.name
                
                try:
                    audio_input = speechsdk.audio.AudioConfig(filename=tmp_wav_path)
                    speech_recognizer = speechsdk.SpeechRecognizer(
                        speech_config=speech_config, 
                        audio_config=audio_input,
                        language="en-US"
                    )
                    
                    result = speech_recognizer.recognize_once()
                    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                        text = result.text.strip()
                        logger.info(f"GroqTranscriber (Azure Fallback): Received transcript ({len(text)} chars): '{text[:80]}...' " if len(text) > 80 else f"GroqTranscriber (Azure Fallback): Received: '{text}'")
                        return text
                    else:
                        logger.warning(f"GroqTranscriber (Azure Fallback): No speech recognized. Reason: {result.reason}")
                        return ""
                finally:
                    # Release file locks held by the C++ SDK
                    if 'speech_recognizer' in locals():
                        del speech_recognizer
                    if 'audio_input' in locals():
                        del audio_input
                        
                    import os
                    if os.path.exists(tmp_wav_path):
                        try:
                            os.unlink(tmp_wav_path)
                        except OSError as e:
                            logger.debug(f"Could not delete temp wav: {e}")
            except Exception as e:
                logger.error(f"GroqTranscriber (Azure Fallback): Failed ({e}).")
        
        logger.warning("GroqTranscriber: Both APIs unavailable. Returning empty string for segment.")
        return ""

    async def transcribe(
        self,
        audio_data: bytes,
        segment: DiarizedSegment,
        matched_speaker_id: str,
    ) -> TranscriptSegment:
        """Transcribe a single diarized segment's PCM audio.

        Args:
            audio_data: Raw 16kHz 16-bit mono PCM bytes.
            segment: The diarized speaker segment (start/end timestamps).
            matched_speaker_id: Speaker ID assigned by the diarization stage.

        Returns:
            A TranscriptSegment with the transcribed text.
        """
        if not audio_data or len(audio_data) == 0:
            return TranscriptSegment(
                speaker_id=matched_speaker_id,
                text="",
                start=segment.start,
                end=segment.end,
                is_final=True,
            )

        try:
            async with self._semaphore:
                text = await asyncio.to_thread(self._transcribe_sync, audio_data)
            if text:
                return TranscriptSegment(
                    speaker_id=matched_speaker_id,
                    text=text,
                    start=segment.start,
                    end=segment.end,
                    is_final=True,
                )
        except Exception as e:
            logger.error(f"GroqTranscriber: Transcription failed for segment [{segment.start:.1f}s-{segment.end:.1f}s]: {e}")

        # Mock fallback — used when APIs are unconfigured or fail
        mock_text = f"[Speech segment {segment.start:.1f}s – {segment.end:.1f}s]"
        logger.debug(f"GroqTranscriber: Using mock text: '{mock_text}'")
        return TranscriptSegment(
            speaker_id=matched_speaker_id,
            text=mock_text,
            start=segment.start,
            end=segment.end,
            is_final=True,
        )
