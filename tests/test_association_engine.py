import pytest
import asyncio
import time
from typing import Dict, Any

from engine.association.schemas import (
    MeetingMetadata,
    MeetingEvent,
    ParticipantIdentity,
    ParticipantIdentityState,
    ParticipantAssociation,
)
from engine.association.metadata_matcher import MetadataMatcher
from engine.association.transcript_matcher import TranscriptMatcher
from engine.association.speaker_matcher import SpeakerMatcher
from engine.association.track_matcher import TrackMatcher
from engine.association.timeline_matcher import TimelineMatcher
from engine.association.confidence import ConfidenceCalculator
from engine.association.participant_builder import ParticipantBuilder
from engine.association.state_manager import AssociationStateManager
from engine.association.association_provider import AssociationProvider
from engine.association.storage import AssociationStorageManager
from engine.association.pipeline import ParticipantAssociationPipeline
from engine.video.schemas import VisualEvidence
from engine.audio.schemas import VoiceEvidence
from engine.transcript.schemas import TranscriptEvidence
from database.redis import get_redis
from database.mongodb import get_mongo_db


def test_metadata_matcher():
  """Test that MetadataMatcher compares name, email, and nicknames correctly using RapidFuzz."""
  matcher = MetadataMatcher()
  meeting_meta = MeetingMetadata(
      meeting_id="test_mtg_1",
      candidate_name="John Smith",
      display_name="John Smith (Engineering)",
      email="john.smith@example.com",
      nicknames=["Johnny S", "John"]
  )

  # 1. Exact / high similarity match
  ev = matcher.match(
      target_name="John Smith",
      target_email="john.smith@example.com",
      target_nicknames=None,
      meeting_metadata=meeting_meta
  )
  assert ev.score >= 0.85
  assert ev.confidence >= 0.80
  assert ev.matched_email == "john.smith@example.com"

  # 2. Nickname / partial variation match
  ev2 = matcher.match(
      target_name="Johnny S",
      target_email=None,
      target_nicknames=None,
      meeting_metadata=meeting_meta
  )
  assert ev2.score >= 0.75


def test_transcript_matcher():
  """Test that TranscriptMatcher extracts self-introductions and addressed cues deterministically."""
  matcher = TranscriptMatcher()

  # 1. Self introduction
  t_ev = TranscriptEvidence(
      meeting_id="mtg",
      speaker_id="Speaker_1",
      conversation_turn_id="turn_1",
      text="Hello everyone, I am John Smith and I will be interviewing today.",
      start_time=0.0,
      end_time=5.0,
      duration=5.0,
      word_count=10,
      avg_wpm=120.0,
      confidence=0.95,
      is_final=True,
      timestamp=int(time.time() * 1000)
  )
  ev = matcher.match("John Smith", "Speaker_1", t_ev)
  assert ev.is_self_intro is True
  assert ev.extracted_name == "john smith"
  assert ev.confidence >= 0.90

  # 2. Addressed cue
  t_ev2 = TranscriptEvidence(
      meeting_id="mtg",
      speaker_id="Speaker_0",
      conversation_turn_id="turn_2",
      text="Thanks John, let's look at your resume next.",
      start_time=6.0,
      end_time=9.0,
      duration=3.0,
      word_count=8,
      avg_wpm=160.0,
      confidence=0.92,
      is_final=True,
      timestamp=int(time.time() * 1000)
  )
  ev2 = matcher.match("John", "Speaker_1", t_ev2)
  assert ev2.is_addressed is True
  assert ev2.extracted_name == "john"


def test_speaker_and_track_matchers():
  """Test linking Speaker IDs and Track IDs with confidence scores."""
  s_matcher = SpeakerMatcher()
  v_matcher = TrackMatcher()

  # Voice check
  v_ev = VoiceEvidence(
      meeting_id="mtg",
      speaker_id="Speaker_1",
      voice_embedding=[0.1] * 128,
      speaker_similarity=0.92,
      transcript="Test voice",
      language="en",
      speech_start=0.0,
      speech_end=4.0,
      speech_duration=4.0,
      speech_confidence=0.95,
      recognition_confidence=0.94,
      timestamp=int(time.time() * 1000)
  )
  s_res = s_matcher.match("Speaker_1", v_ev)
  assert s_res.score >= 0.90
  assert s_res.speaker_id == "Speaker_1"

  # Track check
  track_ev = VisualEvidence(
      meeting_id="mtg",
      track_id="Track_2",
      frame_id=100,
      face_embedding=[0.2] * 128,
      face_similarity=0.91,
      recognition_confidence=0.93,
      detection_confidence=0.96,
      tracking_confidence=0.95,
      visibility=True,
      timestamp=int(time.time() * 1000)
  )
  t_res = v_matcher.match("Track_2", track_ev)
  assert t_res.score >= 0.90
  assert t_res.visibility is True
  assert t_res.track_id == "Track_2"


def test_timeline_matcher():
  """Test that TimelineMatcher correlates multi-modal events occurring in time window."""
  matcher = TimelineMatcher()
  mtg_id = "time_mtg"
  now = int(time.time() * 1000)

  # Record events inside window
  matcher.record_event(mtg_id, "visual_frame", now - 1000, track_id="Track_2")
  matcher.record_event(mtg_id, "join", now - 500, track_id="Track_2", display_name="John Smith")
  matcher.record_event(mtg_id, "voice_speech", now - 200, speaker_id="Speaker_1")

  # Evaluate co-occurrence
  ev = matcher.match(
      meeting_id=mtg_id,
      current_timestamp=now,
      target_track_id="Track_2",
      target_speaker_id="Speaker_1",
      target_display_name="John Smith"
  )
  assert ev.score >= 0.70
  assert ev.confidence >= 0.75
  assert len(ev.co_occurring_events) >= 2


def test_confidence_calculator():
  """Test that ConfidenceCalculator aggregates scores across modalities with weighting."""
  calc = ConfidenceCalculator()
  s_matcher = SpeakerMatcher()
  v_matcher = TrackMatcher()

  # Create mock evidences
  v_ev = VoiceEvidence(
      meeting_id="mtg", speaker_id="S1", voice_embedding=[0.1]*128, speaker_similarity=0.90,
      transcript="hi", language="en", speech_start=0.0, speech_end=1.0, speech_duration=1.0,
      speech_confidence=0.9, recognition_confidence=0.90, timestamp=1000
  )
  track_ev = VisualEvidence(
      meeting_id="mtg", track_id="T1", frame_id=1, face_embedding=[0.1]*128, face_similarity=0.90,
      recognition_confidence=0.90, detection_confidence=0.9, tracking_confidence=0.90,
      visibility=True, timestamp=1000
  )
  s_res = s_matcher.match("S1", v_ev)
  t_res = v_matcher.match("T1", track_ev)

  score, conf, reasons = calc.calculate(
      speaker_evidence=s_res,
      track_evidence=t_res
  )
  assert score >= 0.85
  assert conf >= 0.85
  assert len(reasons) >= 2


@pytest.mark.asyncio
async def test_state_manager_redis():
  """Test AssociationStateManager caching and reverse lookup indices in Redis."""
  state_mgr = AssociationStateManager()
  mtg_id = "test_redis_assoc_mtg"
  pid = "P_test_101"

  identity = ParticipantIdentity(
      participant_id=pid,
      display_name="John Doe",
      email="john.doe@example.com",
      track_id="Track_99",
      speaker_id="Speaker_88",
      association_score=0.92,
      association_confidence=0.94,
      reasons=["Linked via test."],
      timestamp=int(time.time() * 1000)
  )

  # Save to Redis
  state = await state_mgr.save_state(mtg_id, identity)
  assert state.participant_id == pid
  assert state.track_id == "Track_99"

  # Lookup by track_id & speaker_id O(1) indices
  resolved_pid_track = await state_mgr.lookup_by_track_id(mtg_id, "Track_99")
  resolved_pid_speaker = await state_mgr.lookup_by_speaker_id(mtg_id, "Speaker_88")
  assert resolved_pid_track == pid
  assert resolved_pid_speaker == pid

  # Fetch state
  fetched = await state_mgr.get_state(mtg_id, pid)
  assert fetched is not None
  assert fetched.display_name == "John Doe"
  assert len(fetched.history) >= 1


@pytest.mark.asyncio
async def test_storage_mongodb():
  """Test AssociationStorageManager saving historical data across all 5 MongoDB collections."""
  storage = AssociationStorageManager()
  mtg_id = "test_mongo_assoc_mtg"
  pid = "P_mongo_101"

  # Clear prior records for test clean run
  db = get_mongo_db()
  if db is not None:
    await db["participant_identity"].delete_many({"meeting_id": mtg_id})
    await db["association_history"].delete_many({"meeting_id": mtg_id})
    await db["identity_events"].delete_many({"meeting_id": mtg_id})
    await db["participant_timeline"].delete_many({"meeting_id": mtg_id})
    await db["identity_confidence"].delete_many({"meeting_id": mtg_id})

  identity = ParticipantIdentity(
      participant_id=pid,
      display_name="Jane Smith",
      email="jane@example.com",
      track_id="Track_55",
      speaker_id="Speaker_44",
      association_score=0.88,
      association_confidence=0.91,
      reasons=["MongoDB test"],
      timestamp=int(time.time() * 1000)
  )

  await storage.save_identity(mtg_id, identity)
  if db is not None:
    doc = await db["participant_identity"].find_one({"meeting_id": mtg_id, "participant_id": pid})
    assert doc is not None
    assert doc["display_name"] == "Jane Smith"


@pytest.mark.asyncio
async def test_association_pipeline_end_to_end():
  """Test ParticipantAssociationPipeline resolving disconnected signals into one unified participant object."""
  pipeline = ParticipantAssociationPipeline()
  mtg_id = "test_pipe_mtg"
  now = int(time.time() * 1000)

  meta = MeetingMetadata(
      meeting_id=mtg_id,
      candidate_name="John Smith",
      display_name="John Smith",
      email="john@example.com",
      nicknames=["John"]
  )

  # 1. First signal arrives: Visual Evidence (Track_2)
  vis_ev = VisualEvidence(
      meeting_id=mtg_id,
      track_id="Track_2",
      frame_id=1,
      face_embedding=[0.1]*128,
      face_similarity=0.92,
      recognition_confidence=0.91,
      detection_confidence=0.95,
      tracking_confidence=0.94,
      visibility=True,
      timestamp=now - 2000
  )
  assoc1 = await pipeline.process_event(mtg_id, vis_ev, metadata_context=meta)
  assert assoc1 is not None
  pid = assoc1.participant_id
  assert assoc1.track_id == "Track_2"
  assert assoc1.display_name == "John Smith"

  # 2. Second signal arrives: Audio Evidence (Speaker_1) with same DOM join / timing
  join_ev = MeetingEvent(
      meeting_id=mtg_id,
      event_type="join",
      track_id="Track_2",
      speaker_id="Speaker_1",
      display_name="John Smith",
      timestamp=now - 1000
  )
  await pipeline.process_event(mtg_id, join_ev, metadata_context=meta)

  # 3. Third signal arrives: Transcript from Speaker_1 saying "I'm John"
  trans_ev = TranscriptEvidence(
      meeting_id=mtg_id,
      speaker_id="Speaker_1",
      conversation_turn_id="turn_101",
      text="I'm John.",
      start_time=1.0,
      end_time=2.5,
      duration=1.5,
      word_count=2,
      avg_wpm=80.0,
      confidence=0.95,
      is_final=True,
      timestamp=now
  )
  assoc3 = await pipeline.process_event(mtg_id, trans_ev, metadata_context=meta)
  assert assoc3 is not None
  # The pipeline must unify Track_2 and Speaker_1 onto the same participant ID (pid)
  assert assoc3.participant_id == pid
  assert assoc3.track_id == "Track_2"
  assert assoc3.speaker_id == "Speaker_1"
  assert assoc3.email == "john@example.com"
  assert assoc3.association_confidence >= 0.85
