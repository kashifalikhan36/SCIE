import pytest
import time
from database.mongodb import get_mongo_db
from engine.audio.storage import AudioStorageManager
from engine.audio.schemas import VoiceEvidence

@pytest.mark.asyncio
async def test_audio_storage_manager():
  """Test that AudioStorageManager correctly persists audio engine metadata to MongoDB."""
  db = get_mongo_db()
  assert db is not None
  
  storage = AudioStorageManager()
  meeting_id = "pytest_storage_meeting"
  
  # Clear existing test collections
  await db["meetings"].delete_many({"meeting_id": meeting_id})
  await db["speaker_embeddings"].delete_many({"meeting_id": meeting_id})
  await db["transcripts"].delete_many({"meeting_id": meeting_id})
  await db["audio_segments"].delete_many({"meeting_id": meeting_id})
  await db["voice_evidence"].delete_many({"meeting_id": meeting_id})
  
  # 1. Test save_meeting_info
  await storage.save_meeting_info(meeting_id, {"url": "https://meet.google.com/abc-def-ghi"})
  mtg = await db["meetings"].find_one({"meeting_id": meeting_id})
  assert mtg is not None
  assert mtg["url"] == "https://meet.google.com/abc-def-ghi"
  
  # 2. Test save_speaker_embedding (unique constraint checks)
  timestamp = int(time.time() * 1000)
  embedding = [0.2] * 192
  # First insert
  await storage.save_speaker_embedding(meeting_id, "speaker_bob", embedding, timestamp)
  # Second duplicate insert (should be ignored by $setOnInsert)
  await storage.save_speaker_embedding(meeting_id, "speaker_bob", [0.9] * 192, timestamp + 1000)
  
  embeddings = await db["speaker_embeddings"].find({"meeting_id": meeting_id, "speaker_id": "speaker_bob"}).to_list(length=10)
  assert len(embeddings) == 1
  assert embeddings[0]["embedding"] == embedding # remains the first one
  
  # 3. Test save_transcript_segment
  await storage.save_transcript_segment(meeting_id, "speaker_bob", "Hello world", 0.0, 1.5, timestamp)
  tr = await db["transcripts"].find_one({"meeting_id": meeting_id, "speaker_id": "speaker_bob"})
  assert tr is not None
  assert tr["text"] == "Hello world"
  
  # 4. Test save_audio_segment
  await storage.save_audio_segment(meeting_id, {"speaker_id": "speaker_bob", "start": 0.0, "end": 1.5})
  seg = await db["audio_segments"].find_one({"meeting_id": meeting_id, "speaker_id": "speaker_bob"})
  assert seg is not None
  
  # 5. Test save_voice_evidence
  evidence = VoiceEvidence(
      meeting_id=meeting_id,
      speaker_id="speaker_bob",
      voice_embedding=embedding,
      speaker_similarity=0.85,
      transcript="Hello world",
      language="en",
      speech_start=0.0,
      speech_end=1.5,
      speech_duration=1.5,
      speech_confidence=0.98,
      recognition_confidence=1.0,
      timestamp=timestamp
  )
  await storage.save_voice_evidence(evidence)
  ev = await db["voice_evidence"].find_one({"meeting_id": meeting_id, "speaker_id": "speaker_bob"})
  assert ev is not None
  assert ev["speaker_similarity"] == 0.85

  # Clean up after test
  await db["meetings"].delete_many({"meeting_id": meeting_id})
  await db["speaker_embeddings"].delete_many({"meeting_id": meeting_id})
  await db["transcripts"].delete_many({"meeting_id": meeting_id})
  await db["audio_segments"].delete_many({"meeting_id": meeting_id})
  await db["voice_evidence"].delete_many({"meeting_id": meeting_id})
