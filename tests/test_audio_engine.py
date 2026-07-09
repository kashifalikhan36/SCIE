import pytest
import asyncio
import os
from engine.audio.schemas import AudioChunk, VoiceEvidence, ParticipantAudioState
from engine.audio.buffer import AudioBuffer
from engine.audio.pipeline import AudioEnginePipeline
from engine.audio.workers import AudioEngineWorkerManager
from database.mongodb import get_mongo_db
from database.redis import get_redis
from engine.audio.participant_state import ParticipantStateManager

@pytest.mark.asyncio
async def test_audio_buffer_reordering():
  """Test that AudioBuffer buffers, reorders, and groups chunks into windows correctly."""
  # Grouping 4 chunks of 250ms = 1 second window
  buf = AudioBuffer(window_size_ms=1000)
  
  chunk_1 = AudioChunk(meeting_id="test_mtg", timestamp=1000, chunk_index=1, data=b"chunk1")
  chunk_2 = AudioChunk(meeting_id="test_mtg", timestamp=1250, chunk_index=2, data=b"chunk2")
  chunk_3 = AudioChunk(meeting_id="test_mtg", timestamp=1500, chunk_index=3, data=b"chunk3")
  chunk_4 = AudioChunk(meeting_id="test_mtg", timestamp=1750, chunk_index=4, data=b"chunk4")

  # Add out-of-order chunks
  buf.add_chunk(chunk_3)
  buf.add_chunk(chunk_1)
  buf.add_chunk(chunk_4)
  buf.add_chunk(chunk_2)

  # Check if window is assembled
  window = buf.get_next_window()
  assert window is not None
  assert len(window) == 4
  # Verify ordering is preserved
  assert window[0].chunk_index == 1
  assert window[1].chunk_index == 2
  assert window[2].chunk_index == 3
  assert window[3].chunk_index == 4

@pytest.mark.asyncio
async def test_audio_buffer_gap_recovery():
  """Test that AudioBuffer recovers if intermediate chunks are lost."""
  # Gaps > 500ms (2 chunks) triggers recovery
  buf = AudioBuffer(window_size_ms=500) # 2 chunks per window
  
  chunk_1 = AudioChunk(meeting_id="test_mtg", timestamp=1000, chunk_index=1, data=b"chunk1")
  # Chunk 2, 3 lost
  chunk_4 = AudioChunk(meeting_id="test_mtg", timestamp=1750, chunk_index=4, data=b"chunk4")
  chunk_5 = AudioChunk(meeting_id="test_mtg", timestamp=2000, chunk_index=5, data=b"chunk5")

  buf.add_chunk(chunk_1)
  
  # Window not ready (needs 2 chunks: index 1 and 2)
  assert buf.get_next_window() is None
  
  # Add chunk 4 and 5 (creating gap). This should trigger gap recovery and advance expected index
  buf.add_chunk(chunk_4)
  buf.add_chunk(chunk_5)
  
  # Buffer recovers index 4 and 5 as next sequence
  window = buf.get_next_window()
  assert window is not None
  assert len(window) == 2
  assert window[0].chunk_index == 4
  assert window[1].chunk_index == 5

@pytest.mark.asyncio
async def test_audio_pipeline_execution():
  """Test that AudioEnginePipeline executes successfully, updates Redis cache, and persists to MongoDB."""
  pipeline = AudioEnginePipeline()
  meeting_id = "pytest_pipeline_meeting"
  
  # Setup mock active database instances
  mongo_db = get_mongo_db()
  assert mongo_db is not None
  
  # Clear existing test values
  await mongo_db["meetings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["voice_evidence"].delete_many({"meeting_id": meeting_id})
  await mongo_db["transcripts"].delete_many({"meeting_id": meeting_id})
  await mongo_db["speaker_embeddings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["audio_segments"].delete_many({"meeting_id": meeting_id})
  
  redis_client = await get_redis()
  assert redis_client is not None
  # Clear Redis hashes
  await redis_client.delete(f"scie:meeting:{meeting_id}:embeddings")
  
  # 4 mock chunks with non-zero bytes to satisfy fallback VAD energy-check
  chunks = [
      AudioChunk(meeting_id=meeting_id, timestamp=1000, chunk_index=1, data=b"\x01\x02\x03\x04" * 1000),
      AudioChunk(meeting_id=meeting_id, timestamp=1250, chunk_index=2, data=b"\x01\x02\x03\x04" * 1000),
      AudioChunk(meeting_id=meeting_id, timestamp=1500, chunk_index=3, data=b"\x01\x02\x03\x04" * 1000),
      AudioChunk(meeting_id=meeting_id, timestamp=1750, chunk_index=4, data=b"\x01\x02\x03\x04" * 1000)
  ]

  # Run pipeline
  evidences = await pipeline.process_window(meeting_id, chunks)
  
  # Check output evidence
  assert len(evidences) > 0
  evidence = evidences[0]
  assert evidence.meeting_id == meeting_id
  assert evidence.speaker_id is not None
  assert len(evidence.voice_embedding) == 192
  assert evidence.speech_duration == 1.0 # 4 chunks * 0.25s
  
  # Verify Redis cache has the participant state
  state_key = f"scie:meeting:{meeting_id}:participant:{evidence.speaker_id}:state"
  redis_val = await redis_client.get(state_key)
  assert redis_val is not None
  state = ParticipantAudioState.model_validate_json(redis_val)
  assert state.speaker_id == evidence.speaker_id
  assert state.speech_duration == 1.0
  
  # Verify MongoDB contains the historical records
  ev_doc = await mongo_db["voice_evidence"].find_one({"meeting_id": meeting_id})
  assert ev_doc is not None
  assert ev_doc["speaker_id"] == evidence.speaker_id
  assert ev_doc["transcript"] == evidence.transcript
  
  tr_doc = await mongo_db["transcripts"].find_one({"meeting_id": meeting_id})
  assert tr_doc is not None
  assert tr_doc["speaker_id"] == evidence.speaker_id
  
  emb_doc = await mongo_db["speaker_embeddings"].find_one({"meeting_id": meeting_id})
  assert emb_doc is not None
  assert len(emb_doc["embedding"]) == 192
  
  seg_doc = await mongo_db["audio_segments"].find_one({"meeting_id": meeting_id})
  assert seg_doc is not None
  assert seg_doc["speaker_id"] == evidence.speaker_id

  # Clean up after test
  await mongo_db["voice_evidence"].delete_many({"meeting_id": meeting_id})
  await mongo_db["transcripts"].delete_many({"meeting_id": meeting_id})
  await mongo_db["speaker_embeddings"].delete_many({"meeting_id": meeting_id})
  await mongo_db["audio_segments"].delete_many({"meeting_id": meeting_id})
  await redis_client.delete(state_key)
  await redis_client.delete(f"scie:meeting:{meeting_id}:embeddings")

@pytest.mark.asyncio
async def test_audio_workers_flow():
  """Test the asynchronous background worker queue-processing flow."""
  manager = AudioEngineWorkerManager.get_instance()
  manager.start()
  
  meeting_id = "pytest_worker_meeting"
  
  # Clean existing DB entries
  mongo_db = get_mongo_db()
  await mongo_db["voice_evidence"].delete_many({"meeting_id": meeting_id})
  
  # Enqueue 4 chunks to complete a window (window_size = 1s = 4 chunks)
  for i in range(1, 5):
    chunk = AudioChunk(
        meeting_id=meeting_id,
        timestamp=1000 + (i * 250),
        chunk_index=i,
        data=b"\x01\x02\x03\x04" * 1000
    )
    await manager.enqueue_chunk(chunk)
  
  # Allow background worker threads time to process the window
  await asyncio.sleep(1.0)
  
  # Verify if evidence was generated and persisted by the background pipeline
  ev_doc = await mongo_db["voice_evidence"].find_one({"meeting_id": meeting_id})
  assert ev_doc is not None
  
  # Clean up
  await mongo_db["voice_evidence"].delete_many({"meeting_id": meeting_id})
  
  # Stop workers
  await manager.stop()
