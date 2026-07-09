"""
Deep Test Suite — Behavior Engine
===================================
Covers every module at the edge-case, boundary, analytical, and integration level.
"""

import asyncio
import math
import uuid
import pytest
from typing import List, Dict, Any
from unittest.mock import AsyncMock, patch

from engine.behavior.utils import (
    now_ms, generate_evidence_id, generate_timeline_id,
    safe_divide, clamp, format_timestamp_ms, is_question, truncate
)
from engine.behavior.constants import (
    ENGAGEMENT_LOW, ENGAGEMENT_MEDIUM, ENGAGEMENT_HIGH,
    EVENT_JOIN, EVENT_LEAVE, EVENT_CAMERA_ON, EVENT_CAMERA_OFF,
    EVENT_MIC_ON, EVENT_MIC_OFF, EVENT_SCREEN_SHARE_ON, EVENT_SCREEN_SHARE_OFF,
    EVENT_SPEAKING_START,
)
from engine.behavior.schemas import (
    VideoObservation, AudioObservation, TranscriptObservation,
    MetadataObservation, BehaviorFeatures, BehaviorEvidence,
    BehaviorTimelineEntry, ParticipantBehaviorState
)
from engine.behavior.models import (
    SpeakingMetrics, ResponseMetrics, InterruptionMetrics,
    ParticipationMetrics, CameraMetrics, ScreenShareMetrics,
    EngagementMetrics, EmotionMetrics, GazeMetrics, InterruptionEvent
)
from engine.behavior.feature_extractor import BehaviorFeatureExtractor
from engine.behavior.speaking_metrics import SpeakingMetricsCalculator
from engine.behavior.response_metrics import ResponseMetricsCalculator
from engine.behavior.interruption_metrics import InterruptionMetricsCalculator
from engine.behavior.participation_metrics import ParticipationMetricsCalculator
from engine.behavior.camera_metrics import CameraMetricsCalculator
from engine.behavior.screen_share_metrics import ScreenShareMetricsCalculator
from engine.behavior.engagement_metrics import EngagementMetricsCalculator
from engine.behavior.emotion_metrics import EmotionMetricsCalculator
from engine.behavior.gaze_metrics import GazeMetricsCalculator
from engine.behavior.timeline_builder import BehaviorTimelineBuilder
from engine.behavior.evidence_provider import BehaviorEvidenceProvider
from engine.behavior.participant_state import BehaviorStateManager
from engine.behavior.storage import BehaviorStorageManager
from engine.behavior.pipeline import BehaviorPipeline
from engine.behavior.workers import BehaviorWorkerManager, enqueue_behavior_observation
from engine.behavior.config import behavior_config
from database.mongodb import get_mongo_db


# ─────────────────────────────────────────────────────────────────────────────
# 1. TestUtils
# ─────────────────────────────────────────────────────────────────────────────

class TestBehaviorUtils:
  def test_safe_divide(self):
    assert safe_divide(10.0, 2.0) == 5.0
    assert safe_divide(10.0, 0.0, default=-1.0) == -1.0
    assert safe_divide(0.0, 10.0) == 0.0

  def test_clamp(self):
    assert clamp(-0.5, 0.0, 1.0) == 0.0
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(0.75, 0.0, 1.0) == 0.75

  def test_format_timestamp_ms(self):
    assert format_timestamp_ms(0) == "00:00:00"
    assert format_timestamp_ms(45000) == "00:00:45"
    assert format_timestamp_ms(3661000) == "01:01:01"

  def test_is_question(self):
    assert is_question("How do we scale this system?") is True
    assert is_question("Could you explain the architecture?") is True
    assert is_question("We should deploy this to production.") is False
    assert is_question(None) is False
    assert is_question("") is False

  def test_unique_ids(self):
    eid = generate_evidence_id()
    tid = generate_timeline_id()
    assert eid.startswith("BE_") and len(eid) == 11
    assert tid.startswith("BTL_") and len(tid) == 12


# ─────────────────────────────────────────────────────────────────────────────
# 2. TestFeatureExtractor
# ─────────────────────────────────────────────────────────────────────────────

class TestBehaviorFeatureExtractor:
  def setup_method(self):
    self.ex = BehaviorFeatureExtractor()

  def test_metadata_join_leave_toggles(self):
    obs_join = MetadataObservation(
        meeting_id="m1", participant_id="p1", timestamp=1000, event_type=EVENT_JOIN
    )
    f = self.ex.extract(obs_join)
    assert f.join_time == 1000
    assert f.leave_time is None

    obs_cam = MetadataObservation(
        meeting_id="m1", participant_id="p1", timestamp=2000, event_type=EVENT_CAMERA_ON
    )
    f = self.ex.extract(obs_cam)
    assert f.camera_on is True
    assert f.camera_off is False

    obs_mic = MetadataObservation(
        meeting_id="m1", participant_id="p1", timestamp=3000, event_type=EVENT_MIC_ON
    )
    f = self.ex.extract(obs_mic)
    assert f.mic_on is True

    obs_leave = MetadataObservation(
        meeting_id="m1", participant_id="p1", timestamp=4000, event_type=EVENT_LEAVE
    )
    f = self.ex.extract(obs_leave)
    assert f.leave_time == 4000

  def test_audio_speech_accumulation(self):
    obs = AudioObservation(
        meeting_id="m1", speaker_id="s1", participant_id="p2",
        timestamp=1000, speech_start=0.0, speech_end=5.0, speech_duration=5.0
    )
    f = self.ex.extract(obs)
    assert f.speech_time == 5.0
    assert f.longest_monologue == 5.0
    assert f.speaker_id == "s1"

  def test_transcript_word_and_turn_accounting(self):
    obs1 = TranscriptObservation(
        meeting_id="m1", speaker_id="s1", participant_id="p3",
        timestamp=1000, text="Hello world, how are you?", start_time=0.0, end_time=3.0,
        duration=3.0, word_count=5, is_final=True, is_question=True
    )
    f = self.ex.extract(obs1)
    assert f.word_count == 5
    assert f.turn_count == 1
    assert f.question_count == 1
    assert f.response_count == 0

    obs2 = TranscriptObservation(
        meeting_id="m1", speaker_id="s1", participant_id="p3",
        timestamp=2000, text="I am doing great.", start_time=4.0, end_time=6.0,
        duration=2.0, word_count=4, is_final=True, is_question=False
    )
    f = self.ex.extract(obs2)
    assert f.word_count == 9
    assert f.turn_count == 2
    assert f.question_count == 1
    assert f.response_count == 1

  def test_video_observation_and_presence_silent_time(self):
    # First join
    self.ex.extract(MetadataObservation(meeting_id="m1", participant_id="p4", timestamp=1000, event_type=EVENT_JOIN))
    # 10 seconds pass, video observation arrives with visibility=True
    vobs = VideoObservation(meeting_id="m1", track_id="t1", participant_id="p4", timestamp=11000, visibility=True)
    f = self.ex.extract(vobs)
    assert f.track_id == "t1"
    assert f.visible_time == 10.0
    assert f.silent_time == 10.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. TestSpeakingMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeakingMetrics:
  def setup_method(self):
    self.calc = SpeakingMetricsCalculator()

  def test_speaking_calculations(self):
    f = BehaviorFeatures(
        participant_id="p1", speech_time=120.0, turn_count=10, word_count=300, silent_time=60.0
    )
    m = self.calc.calculate(f, meeting_duration_sec=600.0)
    assert m.total_speaking_duration == 120.0
    assert m.number_of_speaking_turns == 10
    assert m.average_speaking_duration == 12.0
    assert m.speaking_percentage == 0.20
    assert m.average_words_per_minute == 150.0  # 300 words / 2 mins
    assert m.average_pause_duration == 6.0      # 60 silent / 10 turns

  def test_zero_turns_safe(self):
    f = BehaviorFeatures(participant_id="p1", speech_time=0.0, turn_count=0)
    m = self.calc.calculate(f, meeting_duration_sec=600.0)
    assert m.average_speaking_duration == 0.0
    assert m.average_words_per_minute == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. TestResponseMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestResponseMetrics:
  def setup_method(self):
    self.calc = ResponseMetricsCalculator()

  def test_response_delay_and_consistency(self):
    f = BehaviorFeatures(participant_id="p1", response_count=4, turn_count=5, word_count=100, speech_time=50.0)
    delays = [2.0, 2.0, 2.0, 2.0]
    m = self.calc.calculate(f, response_delays=delays)
    assert m.average_response_delay == 2.0
    assert m.fastest_response == 2.0
    assert m.slowest_response == 2.0
    assert m.response_consistency == 1.0  # variance 0 -> consistency 1

  def test_response_with_variance(self):
    f = BehaviorFeatures(participant_id="p1", response_count=2, turn_count=2, word_count=40, speech_time=20.0)
    delays = [1.0, 5.0]  # mean=3, variance=((2)^2 + (-2)^2)/2 = 4, sqrt=2 -> 1/(1+2) = 1/3
    m = self.calc.calculate(f, response_delays=delays)
    assert m.average_response_delay == 3.0
    assert m.response_consistency == round(1.0 / 3.0, 4)


# ─────────────────────────────────────────────────────────────────────────────
# 5. TestInterruptionMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestInterruptionMetrics:
  def setup_method(self):
    self.calc = InterruptionMetricsCalculator()

  def test_detect_interruption(self):
    ev = self.calc.detect_interruption(
        meeting_id="m1",
        current_speaker_id="p2",
        current_start=10.0,
        previous_speaker_id="p1",
        previous_start=5.0,
        previous_end=12.0
    )
    assert ev is not None
    assert ev.interrupter_id == "p2"
    assert ev.interrupted_id == "p1"
    assert ev.interrupter_turn_duration == 2.0

    f = BehaviorFeatures(participant_id="p2", speaker_id="p2")
    m = self.calc.calculate(f, meeting_duration_sec=3600.0)
    assert m.interruption_count == 1
    assert m.interruption_frequency == 1.0
    assert "p1" in m.interrupted_participants


# ─────────────────────────────────────────────────────────────────────────────
# 6. TestParticipationMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestParticipationMetrics:
  def setup_method(self):
    self.calc = ParticipationMetricsCalculator()

  def test_participation_ratios(self):
    f = BehaviorFeatures(
        participant_id="p1", join_time=0, leave_time=600000,  # 600 seconds
        speech_time=180.0, silent_time=420.0
    )
    m = self.calc.calculate(f, meeting_duration_sec=600.0)
    assert m.total_meeting_presence == 600.0
    assert m.active_time == 180.0
    assert m.idle_time == 420.0
    assert m.participation_percentage == 0.30  # 180 / 600
    assert m.active_conversation_ratio == 0.30
    assert m.speaking_to_listening_ratio == round(180.0 / 420.0, 4)


# ─────────────────────────────────────────────────────────────────────────────
# 7. TestCameraAndScreenMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestCameraAndScreenMetrics:
  def test_camera_metrics(self):
    calc = CameraMetricsCalculator()
    f = BehaviorFeatures(
        participant_id="p1", join_time=0, leave_time=1000000,  # 1000s
        visible_time=800.0, camera_on=True
    )
    m = calc.calculate(f, meeting_duration_sec=1000.0, camera_toggles_count=2)
    assert m.camera_enabled_duration == 800.0
    assert m.visible_percentage == 0.80
    assert m.number_of_camera_toggles == 2
    assert m.face_visibility_ratio == 1.0

  def test_screen_share_metrics(self):
    calc = ScreenShareMetricsCalculator()
    calc.record_session_start("p1", start_time_sec=100.0)
    calc.record_session_end("p1", end_time_sec=250.0)
    f = BehaviorFeatures(participant_id="p1", screen_share=False)
    m = calc.calculate(f, current_meeting_time_sec=300.0)
    assert m.number_of_screen_share_sessions == 1
    assert m.total_screen_share_duration == 150.0
    assert m.first_screen_share_time == 100.0
    assert m.latest_screen_share_time == 250.0


# ─────────────────────────────────────────────────────────────────────────────
# 8. TestEngagementMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestEngagementMetrics:
  def setup_method(self):
    self.calc = EngagementMetricsCalculator()

  def test_engagement_high_level(self):
    f = BehaviorFeatures(participant_id="p1", turn_count=15, question_count=5)
    spk = SpeakingMetrics(speaking_percentage=0.25)
    resp = ResponseMetrics(average_response_delay=1.0)
    cam = CameraMetrics(visible_percentage=0.90)
    scr = ScreenShareMetrics(total_screen_share_duration=60.0)

    m = self.calc.calculate(f, spk, resp, cam, scr, meeting_duration_sec=1800.0)
    assert m.engagement_score >= 0.75
    assert m.engagement_level == ENGAGEMENT_HIGH
    assert 0.0 <= m.engagement_score <= 1.0

  def test_engagement_low_level(self):
    f = BehaviorFeatures(participant_id="p2", turn_count=0, question_count=0)
    spk = SpeakingMetrics(speaking_percentage=0.0)
    resp = ResponseMetrics(average_response_delay=25.0)
    cam = CameraMetrics(visible_percentage=0.0)
    scr = ScreenShareMetrics(total_screen_share_duration=0.0)

    m = self.calc.calculate(f, spk, resp, cam, scr, meeting_duration_sec=1800.0)
    assert m.engagement_level == ENGAGEMENT_LOW
    assert 0.0 <= m.engagement_score < 0.45


# ─────────────────────────────────────────────────────────────────────────────
# 9. TestEmotionAndGazeMetrics
# ─────────────────────────────────────────────────────────────────────────────

class TestEmotionAndGazeMetrics:
  def test_emotion_aggregation(self):
    calc = EmotionMetricsCalculator()
    calc.record_emotion("p1", "happy")
    calc.record_emotion("p1", "happy")
    calc.record_emotion("p1", "neutral")
    calc.record_emotion("p1", "neutral")
    f = BehaviorFeatures(participant_id="p1")
    m = calc.calculate(f)
    assert m.happy_percentage == 50.0
    assert m.neutral_percentage == 50.0
    assert m.confused_percentage == 0.0

  def test_gaze_aggregation(self):
    calc = GazeMetricsCalculator()
    calc.record_gaze("p1", "looking_at_screen")
    calc.record_gaze("p1", "looking_at_screen")
    calc.record_gaze("p1", "looking_at_screen")
    calc.record_gaze("p1", "looking_away")
    f = BehaviorFeatures(participant_id="p1")
    m = calc.calculate(f)
    assert m.looking_at_screen_percentage == 75.0
    assert m.looking_away_percentage == 25.0
    assert m.attention_ratio == 0.75


# ─────────────────────────────────────────────────────────────────────────────
# 10. TestTimelineBuilder
# ─────────────────────────────────────────────────────────────────────────────

class TestTimelineBuilder:
  def setup_method(self):
    self.tb = BehaviorTimelineBuilder()

  def test_timeline_chronological_and_format(self):
    e1 = self.tb.add_entry("m1", "p1", EVENT_JOIN, "Joined", timestamp_ms=1000)
    e2 = self.tb.add_entry("m1", "p1", EVENT_CAMERA_ON, "Camera On", timestamp_ms=5000)
    e3 = self.tb.add_entry("m1", "p1", EVENT_SPEAKING_START, "Started Speaking", timestamp_ms=13000)

    t = self.tb.get_timeline("p1")
    assert len(t) == 3
    assert t[0].formatted_time == "00:00:00 Joined"
    assert t[1].formatted_time == "00:00:04 Camera On"
    assert t[2].formatted_time == "00:00:12 Started Speaking"


# ─────────────────────────────────────────────────────────────────────────────
# 11. TestEvidenceProvider
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceProvider:
  def test_provide_canonical_evidence(self):
    prov = BehaviorEvidenceProvider()
    f = BehaviorFeatures(participant_id="p1", turn_count=5, word_count=80, speech_time=30.0, question_count=2, response_count=3)
    spk = SpeakingMetrics(speaking_percentage=0.15)
    resp = ResponseMetrics(average_response_delay=1.5)
    int_m = InterruptionMetrics(interruption_count=1)
    part = ParticipationMetrics(total_meeting_presence=300.0)
    cam = CameraMetrics(visible_percentage=0.80)
    scr = ScreenShareMetrics(total_screen_share_duration=0.0)
    eng = EngagementMetrics(engagement_score=0.82, engagement_level=ENGAGEMENT_HIGH)
    emo = EmotionMetrics(neutral_percentage=80.0, happy_percentage=20.0)
    gaze = GazeMetrics(looking_at_screen_percentage=95.0, attention_ratio=0.95)

    ev = prov.provide(f, spk, resp, int_m, part, cam, scr, eng, emo, gaze, meeting_id="m1")
    assert isinstance(ev, BehaviorEvidence)
    assert ev.evidence_id.startswith("BE_")
    assert ev.participant_id == "p1"
    assert ev.speaking_ratio == 0.15
    assert ev.question_count == 2
    assert ev.answer_count == 3
    assert ev.engagement_score == 0.82
    assert ev.camera_ratio == 0.80
    assert ev.behavior_confidence > 0.50


# ─────────────────────────────────────────────────────────────────────────────
# 12. TestStateAndStorage (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBehaviorStateAndStorage:
  async def test_redis_state_save_and_fetch(self):
    mgr = BehaviorStateManager()
    f = BehaviorFeatures(participant_id="p_state_deep", speech_time=45.0, word_count=120, camera_on=True)
    ev = BehaviorEvidence(
        evidence_id="BE_12345678", meeting_id="m_state", participant_id="p_state_deep",
        speaking_ratio=0.25, speech_duration=45.0, response_time=1.2, question_count=1,
        answer_count=3, interruptions=0, engagement_score=0.78, camera_ratio=0.90,
        screen_share_ratio=0.0, behavior_confidence=0.85, timestamp=now_ms()
    )

    saved = await mgr.save_state(f, ev)
    assert isinstance(saved, ParticipantBehaviorState)
    assert saved.current_behavior in ["speaking", "active", "idle", "screen_sharing"]
    assert saved.engagement_score == 0.78

    fetched = await mgr.get_state("m_state", "p_state_deep")
    if fetched:  # If Redis available
      assert fetched.participant_id == "p_state_deep"
      assert fetched.engagement_score == 0.78

  async def test_mongodb_all_5_collections(self):
    db = get_mongo_db()
    if db is None:
      pytest.skip("MongoDB unavailable")

    storage = BehaviorStorageManager()
    mtg = f"m_storage_{uuid.uuid4().hex[:6]}"
    pid = "p_mongo_01"

    # Clean old test items
    for col in [
        "behavior_events", "behavior_metrics", "participant_timelines",
        "engagement_history", "meeting_statistics"
    ]:
      await db[col].delete_many({"meeting_id": mtg})

    # 1. save_event
    await storage.save_event(mtg, pid, EVENT_JOIN, {"info": "test join"})
    # 2. save_metrics_snapshot
    ev = BehaviorEvidence(
        evidence_id="BE_test_0000", meeting_id=mtg, participant_id=pid,
        speaking_ratio=0.2, speech_duration=30.0, response_time=1.0, question_count=1,
        answer_count=2, interruptions=0, engagement_score=0.7, camera_ratio=0.8,
        screen_share_ratio=0.0, behavior_confidence=0.8, timestamp=now_ms()
    )
    await storage.save_metrics_snapshot(ev)
    # 3. save_timeline_entry
    t_entry = BehaviorTimelineEntry(
        entry_id="BTL_test_000", meeting_id=mtg, participant_id=pid,
        timestamp_ms=now_ms(), formatted_time="00:00:00 Joined", event_type=EVENT_JOIN, description="Joined"
    )
    await storage.save_timeline_entry(t_entry)
    # 4. save_engagement_history
    await storage.save_engagement_history(mtg, pid, 0.7, ENGAGEMENT_HIGH, {"speaking": 0.7})
    # 5. save_meeting_statistics
    await storage.save_meeting_statistics(mtg, 2, 1, 0, 0.75)

    assert await db["behavior_events"].count_documents({"meeting_id": mtg}) == 1
    assert await db["behavior_metrics"].count_documents({"meeting_id": mtg}) == 1
    assert await db["participant_timelines"].count_documents({"meeting_id": mtg}) == 1
    assert await db["engagement_history"].count_documents({"meeting_id": mtg}) == 1
    assert await db["meeting_statistics"].count_documents({"meeting_id": mtg}) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 13. TestPipelineAndWorkers (Async)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestBehaviorPipelineAndWorkers:
  async def test_pipeline_end_to_end(self):
    pipe = BehaviorPipeline()
    mtg = f"m_pipe_{uuid.uuid4().hex[:6]}"
    pid = "p_pipe_01"

    # Step 1: Join
    ev1 = await pipe.process(MetadataObservation(meeting_id=mtg, participant_id=pid, timestamp=1000, event_type=EVENT_JOIN))
    assert ev1 is not None
    assert ev1.participant_id == pid

    # Step 2: Camera on and subsequent video frame at ts=5000
    await pipe.process(MetadataObservation(meeting_id=mtg, participant_id=pid, timestamp=3000, event_type=EVENT_CAMERA_ON))
    ev2 = await pipe.process(VideoObservation(meeting_id=mtg, track_id="t1", participant_id=pid, timestamp=5000, visibility=True))
    assert ev2.camera_ratio > 0.0

    # Step 3: Speaking chunk
    ev3 = await pipe.process(AudioObservation(meeting_id=mtg, speaker_id=pid, participant_id=pid, timestamp=10000, speech_start=5.0, speech_end=10.0, speech_duration=5.0))
    assert ev3.speech_duration >= 5.0

    # Step 4: Transcript final chunk (question)
    ev4 = await pipe.process(TranscriptObservation(meeting_id=mtg, speaker_id=pid, participant_id=pid, timestamp=12000, text="Can you see my screen?", start_time=5.0, end_time=10.0, duration=5.0, word_count=5, is_final=True, is_question=True))
    assert ev4.question_count == 1
    assert ev4.engagement_score > 0.0

  async def test_worker_manager_lifecycle(self):
    BehaviorWorkerManager._instance = None
    mgr = BehaviorWorkerManager.get_instance()
    mgr.start()
    assert mgr.is_running is True
    assert len(mgr.worker_tasks) == behavior_config.WORKER_COUNT

    mtg = f"m_work_{uuid.uuid4().hex[:6]}"
    await enqueue_behavior_observation(MetadataObservation(meeting_id=mtg, participant_id="p_w1", timestamp=1000, event_type=EVENT_JOIN))
    # Give worker loop a tick to process
    await asyncio.sleep(0.1)

    await mgr.stop()
    assert mgr.is_running is False
    assert all(t.done() for t in mgr.worker_tasks)
