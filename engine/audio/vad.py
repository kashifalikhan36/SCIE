import logging
from typing import List
from engine.audio.models import ModelRegistry
from engine.audio.schemas import SpeechSegment
from engine.audio.config import audio_config
from engine.audio.exceptions import VADError

logger = logging.getLogger("SCIE.audio_engine.vad")

class VoiceActivityDetector:
  """Performs Voice Activity Detection using Pyannote or energy-based fallback."""

  def __init__(self):
    self.registry = ModelRegistry.get_instance()

  async def detect_speech(self, audio_data: bytes, duration_sec: float) -> List[SpeechSegment]:
    """Detects active speech segments in the provided audio chunk/window."""
    if not audio_data or len(audio_data) == 0:
      return []

    # If Pyannote VAD model is loaded, try using it
    if self.registry.vad_loaded and self.registry.vad_model is not None:
      import tempfile
      import os
      import wave
      try:
        logger.info("Executing Pyannote VAD model...")
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp_path = tmp.name
            with wave.open(tmp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(audio_data)
        
        # Pyannote segmentation model returns a SlidingWindowFeature
        # We need to binarize it
        from pyannote.audio.pipelines.utils.wrapper import Inference
        inference = Inference(self.registry.vad_model, step=0.1)
        vad_output = inference(tmp_path)
        
        # Binarize using threshold from config, or default 0.5
        threshold = getattr(audio_config, 'VAD_SPEECH_THRESHOLD', 0.5)
        
        from pyannote.core import notebook
        from pyannote.audio.utils.signal import binarize
        
        active_speech = binarize(vad_output, onset=threshold, offset=threshold, min_duration_on=0.1, min_duration_off=0.1)
        
        segments = []
        for segment in active_speech:
            segments.append(
                SpeechSegment(
                    start=segment.start,
                    end=segment.end,
                    confidence=0.95 # Mocked confidence, as binarize loses exact logits
                )
            )
            
        os.unlink(tmp_path)
        
        if not segments:
            logger.info("VAD: No speech detected by Pyannote in this window.")
            
        return segments
      except Exception as e:
        logger.error(f"Pyannote VAD execution failed: {e}. Falling back to energy-based VAD.")

    # Fallback Heuristic: Energy-Based VAD
    # We check if the data has sufficient non-zero values (not silent padding)
    try:
      non_zero_ratio = sum(1 for b in audio_data if b != 0) / len(audio_data)
      
      # If non-zero byte ratio is very small, it's silent padding
      if non_zero_ratio < 0.05:
        logger.info("VAD: Silence detected (energy below threshold). Skipping window.")
        return []

      logger.info(f"VAD: Speech detected (non-zero energy ratio: {non_zero_ratio:.2f})")
      # Return a single segment spanning the entire window
      return [
          SpeechSegment(
              start=0.0, 
              end=duration_sec, 
              confidence=float(non_zero_ratio)
          )
      ]
    except Exception as e:
      raise VADError(f"Error during VAD execution: {e}")
