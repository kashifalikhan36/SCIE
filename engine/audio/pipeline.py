import logging
import time
from typing import List, Optional
from engine.audio.schemas import AudioChunk, VoiceEvidence
from engine.audio.vad import VoiceActivityDetector
from engine.audio.diarization import SpeakerDiarizer
from engine.audio.speaker_recognition import SpeakerRecognizer
from engine.audio.whisper_transcriber import WhisperTranscriber
from engine.audio.language_detector import LanguageDetector
from engine.audio.evidence_provider import VoiceEvidenceProvider
from engine.audio.participant_state import ParticipantStateManager
from engine.audio.storage import AudioStorageManager
from engine.audio.exceptions import AudioEngineException

logger = logging.getLogger("SCIE.audio_engine.pipeline")

class AudioEnginePipeline:
  """Coordinates the entire processing pipeline from incoming raw chunks to structured evidence."""

  def __init__(self):
    self.vad = VoiceActivityDetector()
    self.diarizer = SpeakerDiarizer()
    self.recognizer = SpeakerRecognizer()
    self.transcriber = WhisperTranscriber()
    self.lang_detector = LanguageDetector()
    
    self.state_manager = ParticipantStateManager()
    self.storage_manager = AudioStorageManager()

  async def process_window(self, meeting_id: str, chunks: List[AudioChunk]) -> List[VoiceEvidence]:
    """Processes a window of sequential audio chunks, separating tab and mic streams."""
    if not chunks:
      return []

    # Ensure chunks are ordered by index
    chunks = sorted(chunks, key=lambda x: x.chunk_index)
    
    tab_chunks = [c for c in chunks if c.chunk_type == "audio"]
    mic_chunks = [c for c in chunks if c.chunk_type == "mic_audio"]

    evidence_list = []
    if tab_chunks:
      evidence_list.extend(await self._process_sub_window(meeting_id, tab_chunks, stream_name="tab"))
    if mic_chunks:
      evidence_list.extend(await self._process_sub_window(meeting_id, mic_chunks, stream_name="mic"))
      
    return evidence_list

  async def _process_sub_window(self, meeting_id: str, chunks: List[AudioChunk], stream_name: str) -> List[VoiceEvidence]:
    """Internal method to process a homogenous stream of chunks (either all tab or all mic)."""
    # 1. Decode WebM chunks to a single continuous PCM byte stream
    from engine.audio.utils import decode_chunks_to_pcm
    chunk_bytes_list = [c.data for c in chunks]
    combined_audio = decode_chunks_to_pcm(chunk_bytes_list)
    
    # Each chunk represents 500ms (0.5 seconds)
    duration_sec = len(chunks) * 0.5

    logger.info(f"Processing '{stream_name}' audio pipeline window for meeting {meeting_id} with {len(chunks)} chunks ({duration_sec}s of audio)")

    if not combined_audio:
        logger.warning(f"Could not extract PCM audio from {stream_name} chunks.")
        return []

    try:
      # 2. Stage: Voice Activity Detection (VAD)
      # Pass PCM data to VAD
      speech_segments = await self.vad.detect_speech(combined_audio, duration_sec)
      
      # If no speech is detected, return early
      if not speech_segments:
        logger.info(f"VAD ({stream_name}): No speech detected in this window. Pipeline execution terminated early.")
        return []

      # 3. Stage: Speaker Diarization
      diarized_segments = await self.diarizer.diarize(combined_audio, speech_segments)
      if not diarized_segments:
        logger.info(f"Diarization ({stream_name}): No diarized segments found. Pipeline execution terminated early.")
        return []

      collected_evidence: List[VoiceEvidence] = []

      # Process each diarized speaker segment in the window
      for diarized_seg in diarized_segments:
        # Find matching speech segment for confidence metrics
        matching_speech = next(
            (s for s in speech_segments if abs(s.start - diarized_seg.start) < 0.1),
            speech_segments[0]
        )

        # 4. Stage: Speaker Recognition
        # If it's the mic stream, it is always the local user ("you")
        recognition_res = await self.recognizer.recognize(meeting_id, combined_audio, diarized_seg)
        if stream_name == "mic":
            recognition_res.matched_speaker_id = "you"
            recognition_res.speaker_label = "you"

        # 5. Stage: Speech To Text — pass valid PCM combined audio.
        transcript_res = await self.transcriber.transcribe(
            combined_audio,
            diarized_seg,
            recognition_res.matched_speaker_id
        )

        # 6. Stage: Language Detection
        lang_res = await self.lang_detector.detect_language(combined_audio)

        # 7. Stage: Voice Evidence Assembly
        evidence = VoiceEvidenceProvider.assemble_evidence(
            meeting_id=meeting_id,
            speech=matching_speech,
            diarization=diarized_seg,
            recognition=recognition_res,
            transcript=transcript_res,
            lang_detect=lang_res
        )

        # 8. Stage: Redis Integration (Update Live Participant State)
        await self.state_manager.update_state(meeting_id, evidence)

        # 9. Stage: MongoDB Persistence (Store Historical Data)
        await self.storage_manager.save_speaker_embedding(
            meeting_id, 
            evidence.speaker_id, 
            evidence.voice_embedding, 
            evidence.timestamp
        )
        await self.storage_manager.save_transcript_segment(
            meeting_id,
            evidence.speaker_id,
            evidence.transcript,
            evidence.speech_start,
            evidence.speech_end,
            evidence.timestamp
        )
        await self.storage_manager.save_voice_evidence(evidence)

        # Enqueue transcript event to Transcript Engine
        try:
          from engine.transcript import enqueue_transcript_event
          raw_event = {
              "meeting_id": meeting_id,
              "speaker_id": evidence.speaker_id,
              "text": evidence.transcript,
              "start_time": evidence.speech_start,
              "end_time": evidence.speech_end,
              "confidence": evidence.recognition_confidence,
              "is_final": True,
              "timestamp": evidence.timestamp
          }
          await enqueue_transcript_event(meeting_id, raw_event)
        except Exception as e:
          logger.error(f"Failed to enqueue transcript event: {e}")

        await self.storage_manager.save_audio_segment(
            meeting_id, 
            {
                "speaker_id": evidence.speaker_id,
                "start": evidence.speech_start,
                "end": evidence.speech_end,
                "timestamp": evidence.timestamp
            }
        )

        # Enqueue to FusionEngine
        try:
            from engine.fusion.workers import enqueue_fusion_evidence
            from engine.fusion.constants import DOMAIN_VOICE
            await enqueue_fusion_evidence(
                evidence_obj=evidence,
                source_type=DOMAIN_VOICE,
                speaker_id=evidence.speaker_id,
                score=evidence.recognition_confidence,
                reliability=1.0
            )
        except Exception as fe:
            logger.error(f"Failed to enqueue voice evidence to FusionEngine: {fe}")

        collected_evidence.append(evidence)

      return collected_evidence

    except Exception as e:
      logger.error(f"Pipeline processing failed for '{stream_name}' window in meeting {meeting_id}: {e}")
      return []
