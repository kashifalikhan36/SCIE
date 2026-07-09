import pytest
import uuid
import json
from engine.audio.speaker_recognition import SpeakerRecognizer
from engine.audio.schemas import DiarizedSegment, SpeakerRecognitionResult
from engine.audio.utils import calculate_cosine_similarity
from database.redis import get_redis

def test_cosine_similarity():
  """Test cosine similarity calculator utility functions."""
  # Identical vectors
  assert calculate_cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
  # Orthogonal vectors
  assert calculate_cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
  # Mismatched lengths
  assert calculate_cosine_similarity([1.0], [1.0, 2.0]) == 0.0
  # Empty list
  assert calculate_cosine_similarity([], []) == 0.0

@pytest.mark.asyncio
async def test_speaker_recognition_new_and_existing():
  """Test that SpeakerRecognizer generates new speaker IDs and matches existing ones using Redis."""
  recognizer = SpeakerRecognizer()
  meeting_id = f"pytest_rec_mtg_{uuid.uuid4().hex[:8]}"
  
  # Ensure Redis connection works
  redis_client = await get_redis()
  assert redis_client is not None
  
  segment_1 = DiarizedSegment(speaker_label="SPEAKER_00", start=0.0, end=1.0, confidence=0.9)
  
  # 1. Process as new speaker (empty Redis state)
  res_1 = await recognizer.recognize(meeting_id, b"\x01\x02" * 1000, segment_1)
  assert isinstance(res_1, SpeakerRecognitionResult)
  assert res_1.matched_speaker_id.startswith("speaker_")
  assert len(res_1.embedding) == 192
  assert res_1.similarity == 1.0 # First occurrence matches itself
  
  # 2. Verify it was stored in Redis
  stored_embeddings = await redis_client.hgetall(f"scie:meeting:{meeting_id}:embeddings")
  assert res_1.matched_speaker_id in stored_embeddings
  
  # 3. Process another segment from the same speaker (same mock embedding is generated deterministically)
  segment_2 = DiarizedSegment(speaker_label="SPEAKER_00", start=1.0, end=2.0, confidence=0.85)
  res_2 = await recognizer.recognize(meeting_id, b"\x01\x02" * 1000, segment_2)
  
  # Assert it matches the previously stored ID
  assert res_2.matched_speaker_id == res_1.matched_speaker_id
  assert res_2.similarity > 0.95
  
  # Clean up Redis keys
  await redis_client.delete(f"scie:meeting:{meeting_id}:embeddings")
