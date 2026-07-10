import logging
import uuid
import json
import random
from typing import List, Dict, Tuple, Optional
from database.redis import get_redis
from engine.audio.models import ModelRegistry
from engine.audio.schemas import DiarizedSegment, SpeakerRecognitionResult
from engine.audio.config import audio_config
from engine.audio.utils import calculate_cosine_similarity
from engine.audio.exceptions import SpeakerRecognitionError

logger = logging.getLogger("SCIE.audio_engine.speaker_recognition")

class SpeakerRecognizer:
  """Generates speaker embeddings using SpeechBrain and compares them to identify matches."""

  def __init__(self):
    self.registry = ModelRegistry.get_instance()
    self.embedding_dim = 256 # WeSpeaker ResNet34 standard dimension

  async def recognize(self, meeting_id: str, audio_data: bytes, segment: DiarizedSegment) -> SpeakerRecognitionResult:
    """Generates speaker embedding and checks against stored embeddings in Redis to match identity."""
    try:
      # 1. Generate Embedding
      embedding = await self._generate_embedding(audio_data, segment)

      # 2. Compare against previous embeddings stored in Redis
      matched_speaker_id, similarity = await self._match_speaker_in_redis(meeting_id, embedding)
      
      confidence = 1.0 if similarity >= audio_config.SPEAKER_SIMILARITY_THRESHOLD else 0.8
      
      # 3. If no match, generate a new speaker ID and store it
      if not matched_speaker_id:
        matched_speaker_id = f"speaker_{uuid.uuid4().hex[:8]}"
        similarity = 1.0
        confidence = 1.0
        await self._store_embedding_in_redis(meeting_id, matched_speaker_id, embedding)
        logger.info(f"Speaker Recognition: Created new speaker identity: {matched_speaker_id}")
      else:
        logger.info(f"Speaker Recognition: Matched segment to {matched_speaker_id} with similarity {similarity:.2f}")

      return SpeakerRecognitionResult(
          speaker_label=segment.speaker_label,
          embedding=embedding,
          similarity=similarity,
          matched_speaker_id=matched_speaker_id,
          confidence=confidence
      )

    except Exception as e:
      raise SpeakerRecognitionError(f"Failed speaker recognition processing: {e}")

  async def _generate_embedding(self, audio_data: bytes, segment: DiarizedSegment) -> List[float]:
    """Generates a 256-dimensional embedding vector for the speech segment."""
    if self.registry.speaker_rec_loaded and self.registry.speaker_recognition_model is not None:
      try:
        import torch
        import numpy as np
        logger.info("Executing SpeechBrain Speaker Recognition model...")
        
        # Calculate byte indices for 16kHz 16-bit mono PCM
        start_byte = int(segment.start * 16000) * 2
        end_byte = int(segment.end * 16000) * 2
        
        # Ensure we don't go out of bounds
        end_byte = min(end_byte, len(audio_data))
        start_byte = min(start_byte, end_byte)
        
        segment_audio = audio_data[start_byte:end_byte]
        
        if len(segment_audio) < 3200: # Need at least 0.1s of audio
            logger.warning("Segment too short for embedding, generating fallback.")
            raise ValueError("Segment too short")
            
        np_audio = np.frombuffer(segment_audio, dtype=np.int16)
        tensor_audio = torch.from_numpy(np_audio.copy()).float() / 32768.0
        tensor_audio = tensor_audio.unsqueeze(0) # (batch, time)
        
        embeddings = self.registry.speaker_recognition_model.encode_batch(tensor_audio)
        return embeddings.squeeze().tolist()
      except Exception as e:
        logger.error(f"SpeechBrain embedding failed: {e}. Falling back to deterministic mock.")

    # Fallback/Mock: Generate a deterministic mock embedding based on speaker label
    # to maintain consistency within the same test or meeting run.
    random.seed(hash(segment.speaker_label))
    embedding = [random.uniform(-0.1, 0.1) for _ in range(self.embedding_dim)]
    # L2 normalize the mock embedding
    norm = sum(x*x for x in embedding) ** 0.5
    if norm > 0:
      embedding = [x / norm for x in embedding]
    return embedding

  async def _match_speaker_in_redis(self, meeting_id: str, current_emb: List[float]) -> Tuple[Optional[str], float]:
    """Checks the generated embedding against all known speakers for this meeting in Redis."""
    redis_client = await get_redis()
    if not redis_client:
      logger.warning("Redis client not available. Skipping Redis embedding matching.")
      return None, 0.0

    try:
      # Key template: scie:meeting:<meeting_id>:embeddings -> Hash mapping speaker_id to json-encoded embedding
      key = f"scie:meeting:{meeting_id}:embeddings"
      stored_data = await redis_client.hgetall(key)
      if not stored_data:
        return None, 0.0

      best_match_id = None
      best_similarity = -1.0

      for speaker_id, emb_json_str in stored_data.items():
        try:
          stored_emb = json.loads(emb_json_str)
          sim = calculate_cosine_similarity(current_emb, stored_emb)
          if sim > best_similarity:
            best_similarity = sim
            best_match_id = speaker_id
        except Exception as parse_err:
          logger.error(f"Error parsing stored embedding for speaker {speaker_id}: {parse_err}")
          continue

      if best_similarity >= audio_config.SPEAKER_SIMILARITY_THRESHOLD:
        return best_match_id, best_similarity

      return None, 0.0
    except Exception as e:
      logger.error(f"Failed to query speaker embeddings in Redis: {e}")
      return None, 0.0

  async def _store_embedding_in_redis(self, meeting_id: str, speaker_id: str, embedding: List[float]):
    """Saves a new speaker's embedding to Redis."""
    redis_client = await get_redis()
    if not redis_client:
      return
    try:
      key = f"scie:meeting:{meeting_id}:embeddings"
      await redis_client.hset(key, speaker_id, json.dumps(embedding))
      logger.info(f"Successfully stored embedding for speaker {speaker_id} in Redis.")
    except Exception as e:
      logger.error(f"Failed to save speaker embedding to Redis: {e}")
