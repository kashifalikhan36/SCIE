import pytest
import asyncio
import time
import uuid
from engine.transcript.schemas import TranscriptChunk, ConversationTurn, TranscriptEvidence, ParticipantTranscriptState
from engine.transcript.receiver import TranscriptReceiver
from engine.transcript.buffer import TranscriptBuffer
from engine.transcript.partial_manager import PartialTranscriptManager
from engine.transcript.final_manager import FinalTranscriptManager
from engine.transcript.timeline_builder import SpeakerTimelineBuilder
from engine.transcript.conversation_builder import ConversationBuilder
from engine.transcript.transcript_provider import TranscriptEvidenceProvider
from engine.transcript.participant_state import ParticipantTranscriptStateManager
from engine.transcript.storage import TranscriptStorageManager
from engine.transcript.pipeline import TranscriptEnginePipeline
from engine.transcript.workers import TranscriptEngineWorkerManager
from engine.transcript.exceptions import TranscriptReceiverError
from database.redis import get_redis
from database.mongodb import get_mongo_db

def test_transcript_receiver():
  """Test that TranscriptReceiver validates schema and confidence thresholds correctly."""
  receiver = TranscriptReceiver()
  
  # 1. Valid chunk
  chunk_data = {
      "meeting_id": "test_meeting",
      "speaker_id": "Speaker_00",
      "text": "Hello world",
      "start_time": 0.0,
      "end_time": 1.5,
      "confidence": 0.95,
      "is_final": True,
      "timestamp": int(time.time() * 1000)
  }
  chunk = receiver.receive_event(chunk_data)
  assert isinstance(chunk, TranscriptChunk)
  assert chunk.text == "Hello world"
  
  # 2. Invalid missing speaker
  bad_data = chunk_data.copy()
  bad_data["speaker_id"] = ""
  with pytest.raises(TranscriptReceiverError):
    receiver.receive_event(bad_data)

def test_transcript_buffer():
  """Test that TranscriptBuffer deduplicates and orders streaming packets chronologically."""
  buf = TranscriptBuffer()
  meeting_id = "test_buf_mtg"
  
  chunk_1 = TranscriptChunk(meeting_id=meeting_id, speaker_id="S1", text="First", start_time=1.0, end_time=2.0, confidence=0.9, is_final=True, timestamp=1000)
  chunk_2 = TranscriptChunk(meeting_id=meeting_id, speaker_id="S1", text="Second", start_time=2.5, end_time=3.5, confidence=0.9, is_final=True, timestamp=2000)
  
  # Add out-of-order
  buf.add_chunk(chunk_2)
  buf.add_chunk(chunk_1)
  
  ordered = buf.get_ordered_chunks(meeting_id)
  assert len(ordered) == 2
  assert ordered[0].text == "First"
  assert ordered[1].text == "Second"
  
  # Duplicate check
  buf.add_chunk(chunk_1)
  assert len(buf.get_ordered_chunks(meeting_id)) == 2

@pytest.mark.asyncio
async def test_partial_and_final_managers():
  """Test rolling partial text caching and finalized utterance archiving inside Redis."""
  redis_client = await get_redis()
  assert redis_client is not None
  
  partial_mgr = PartialTranscriptManager()
  final_mgr = FinalTranscriptManager()
  
  meeting_id = f"pytest_trans_mtg_{uuid.uuid4().hex[:8]}"
  speaker_id = "Speaker_01"
  
  # Clean existing keys
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:partial")
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:final_history")
  
  # 1. Update partial
  await partial_mgr.update_partial(meeting_id, speaker_id, "I have worked")
  val = await partial_mgr.get_partial(meeting_id, speaker_id)
  assert val == "I have worked"
  
  # 2. Finalize utterance
  chunk = TranscriptChunk(
      meeting_id=meeting_id,
      speaker_id=speaker_id,
      text="I have worked at Google.",
      start_time=1.0,
      end_time=3.0,
      confidence=0.98,
      is_final=True,
      timestamp=int(time.time() * 1000)
  )
  
  history = await final_mgr.finalize_utterance(meeting_id, chunk)
  assert len(history) == 1
  assert history[0].text == "I have worked at Google."
  
  # Verify partial was wiped
  partial_wiped = await partial_mgr.get_partial(meeting_id, speaker_id)
  assert partial_wiped == ""
  
  # Cleanup
  await final_mgr.clear_meeting_history(meeting_id, [speaker_id])

def test_timeline_and_conversation_builders():
  """Test timeline chronological sorting and ConversationTurn grouping pause thresholds."""
  timeline_builder = SpeakerTimelineBuilder()
  conv_builder = ConversationBuilder()
  
  chunk_1 = TranscriptChunk(meeting_id="m", speaker_id="S1", text="Hello.", start_time=1.0, end_time=2.0, confidence=0.9, is_final=True, timestamp=1000)
  chunk_2 = TranscriptChunk(meeting_id="m", speaker_id="S1", text="How are you?", start_time=3.0, end_time=4.0, confidence=0.9, is_final=True, timestamp=2000) # Gap: 1s (same speaker -> merges)
  chunk_3 = TranscriptChunk(meeting_id="m", speaker_id="S2", text="I am fine.", start_time=5.0, end_time=6.0, confidence=0.9, is_final=True, timestamp=3000) # Different speaker -> new turn
  chunk_4 = TranscriptChunk(meeting_id="m", speaker_id="S2", text="Thank you.", start_time=12.0, end_time=13.0, confidence=0.9, is_final=True, timestamp=4000) # Gap: 6s (same speaker, but > 5s -> new turn)

  chunks = [chunk_2, chunk_1, chunk_4, chunk_3]
  
  # 1. Timeline sorting
  timeline = timeline_builder.build_timeline(chunks)
  assert len(timeline) == 4
  assert timeline[0]["transcript"] == "Hello."
  assert timeline[3]["transcript"] == "Thank you."
  
  # 2. Turn grouping
  turns = conv_builder.build_conversation_turns(chunks)
  assert len(turns) == 3 # Turn 1: S1 (Hello. How are you?), Turn 2: S2 (I am fine.), Turn 3: S2 (Thank you.)
  
  assert turns[0].speaker_id == "S1"
  assert len(turns[0].utterances) == 2
  assert turns[0].word_count == 4 # "Hello. How are you?"
  
  assert turns[1].speaker_id == "S2"
  assert turns[1].utterances == ["I am fine."]
  
  assert turns[2].speaker_id == "S2"
  assert turns[2].utterances == ["Thank you."]

@pytest.mark.asyncio
async def test_participant_transcript_state_manager():
  """Test Redis ParticipantTranscriptState cumulative stats merging."""
  redis_client = await get_redis()
  state_mgr = ParticipantTranscriptStateManager()
  
  meeting_id = "pytest_state_meeting"
  speaker_id = "Speaker_state"
  
  redis_key = f"scie:meeting:{meeting_id}:participant:{speaker_id}:transcript_state"
  await redis_client.delete(redis_key)
  
  # 1. Send rolling partial
  evidence_p = TranscriptEvidence(
      meeting_id=meeting_id,
      speaker_id=speaker_id,
      conversation_turn_id="turn_rolling",
      text="I have worked",
      start_time=1.0,
      end_time=2.0,
      duration=1.0,
      word_count=3,
      confidence=0.9,
      is_final=False,
      timestamp=1000
  )
  
  state_p = await state_mgr.update_state(meeting_id, evidence_p)
  assert state_p is not None
  assert state_p.latest_partial == "I have worked"
  assert state_p.latest_final is None
  
  # 2. Send final
  evidence_f = TranscriptEvidence(
      meeting_id=meeting_id,
      speaker_id=speaker_id,
      conversation_turn_id="turn_123",
      text="I have worked at Microsoft.",
      start_time=1.0,
      end_time=3.0,
      duration=2.0,
      word_count=5,
      confidence=0.95,
      is_final=True,
      timestamp=2000
  )
  
  state_f = await state_mgr.update_state(meeting_id, evidence_f)
  assert state_f is not None
  assert state_f.latest_partial is None
  assert state_f.latest_final == "I have worked at Microsoft."
  assert state_f.word_count == 5
  assert state_f.speaking_duration == 2.0
  assert state_f.conversation_history == ["I have worked at Microsoft."]
  
  # Cleanup
  await redis_client.delete(redis_key)

@pytest.mark.asyncio
async def test_transcript_storage_manager():
  """Test MongoDB writes for transcripts, turns, raw events, and timelines."""
  db = get_mongo_db()
  assert db is not None
  
  storage = TranscriptStorageManager()
  meeting_id = "pytest_trans_storage_meeting"
  
  # Clear existing records
  await db["meetings"].delete_many({"meeting_id": meeting_id})
  await db["transcripts"].delete_many({"meeting_id": meeting_id})
  await db["conversation_turns"].delete_many({"meeting_id": meeting_id})
  await db["speaker_timelines"].delete_many({"meeting_id": meeting_id})
  await db["transcript_events"].delete_many({"meeting_id": meeting_id})
  
  # 1. Save turns
  turn = ConversationTurn(conversation_turn_id="turn_1", speaker_id="S1", utterances=["Hi"], start_time=1.0, end_time=2.0, duration=1.0, word_count=1)
  await storage.save_conversation_turn(meeting_id, turn)
  doc_turn = await db["conversation_turns"].find_one({"meeting_id": meeting_id, "conversation_turn_id": "turn_1"})
  assert doc_turn is not None
  assert doc_turn["speaker_id"] == "S1"
  
  # 2. Save timeline list
  await storage.save_timeline(meeting_id, [{"speaker_id": "S1", "text": "Hi"}])
  doc_time = await db["speaker_timelines"].find_one({"meeting_id": meeting_id})
  assert doc_time is not None
  assert doc_time["timeline"][0]["text"] == "Hi"
  
  # Cleanup
  await db["meetings"].delete_many({"meeting_id": meeting_id})
  await db["transcripts"].delete_many({"meeting_id": meeting_id})
  await db["conversation_turns"].delete_many({"meeting_id": meeting_id})
  await db["speaker_timelines"].delete_many({"meeting_id": meeting_id})
  await db["transcript_events"].delete_many({"meeting_id": meeting_id})

@pytest.mark.asyncio
async def test_transcript_pipeline_and_workers():
  """Test end-to-end pipeline execution and worker manager queue flows."""
  pipeline = TranscriptEnginePipeline()
  TranscriptEngineWorkerManager._instance = None
  worker_mgr = TranscriptEngineWorkerManager.get_instance()
  worker_mgr.start()
  
  meeting_id = "pytest_trans_worker_meeting"
  speaker_id = "S_pipeline"
  
  redis_client = await get_redis()
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:partial")
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:final_history")
  await redis_client.delete(f"scie:meeting:{meeting_id}:participant:{speaker_id}:transcript_state")
  
  mongo_db = get_mongo_db()
  await mongo_db["transcripts"].delete_many({"meeting_id": meeting_id})
  
  # 1. Process partial chunk directly via pipeline
  partial_event = {
      "meeting_id": meeting_id,
      "speaker_id": speaker_id,
      "text": "I am speaking",
      "start_time": 0.0,
      "end_time": 1.0,
      "confidence": 0.90,
      "is_final": False,
      "timestamp": int(time.time() * 1000)
  }
  
  ev_p = await pipeline.process_chunk(meeting_id, partial_event)
  assert ev_p is not None
  assert ev_p.is_final is False
  assert ev_p.text == "I am speaking"
  
  # 2. Enqueue final chunk via worker manager
  final_event = {
      "meeting_id": meeting_id,
      "speaker_id": speaker_id,
      "text": "I am speaking now.",
      "start_time": 0.0,
      "end_time": 1.5,
      "confidence": 0.97,
      "is_final": True,
      "timestamp": int(time.time() * 1000)
  }
  
  await worker_mgr.enqueue_event(meeting_id, final_event)
  
  # Allow background worker loops time to pull and execute the task (poll up to 3 seconds)
  doc = None
  for _ in range(30):
    doc = await mongo_db["transcripts"].find_one({"meeting_id": meeting_id, "speaker_id": speaker_id, "is_final": True})
    if doc is not None:
      break
    await asyncio.sleep(0.1)
  
  # Verify final transcript is written to MongoDB
  assert doc is not None
  assert doc["text"] == "I am speaking now."
  
  # Cleanup
  await worker_mgr.stop()
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:partial")
  await redis_client.delete(f"scie:meeting:{meeting_id}:speaker:{speaker_id}:final_history")
  await redis_client.delete(f"scie:meeting:{meeting_id}:participant:{speaker_id}:transcript_state")
  await mongo_db["transcripts"].delete_many({"meeting_id": meeting_id})
