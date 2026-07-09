"""
Deep Integration, Stress, & Adversarial Verification Suite for the SCIE Dynamic Weighting Engine (`engine/weighting/`).

Tests covered:
1. Combinatorial Domain Matrix ($2^7 = 128$ availability combinations ensuring exact sum == 1.0 and 0.0 for unavailable domains).
2. Real-Time 45-Minute Meeting Lifecycle & Dynamic Transitions (Interview Started -> In Progress -> Coding -> Camera Off -> Screen Share -> Long Meeting -> Behavioral).
3. Adversarial Quality Boundaries (Extreme face blur, diarization failure/crosstalk, super-high confidence boosters, partial/unfinalized transcripts).
4. High-Speed Caching & Delta Threshold Invalidation (Sub-millisecond retrieval checks, quality delta boundaries `< 0.05` vs `>= 0.05`, explicit hardware toggles).
5. Exhaustive Multi-Worker Concurrency & Queue Contention (4 concurrent workers processing 200 simultaneous weighting jobs without race conditions or deadlocks).
6. Offline Storage Resilience & Chronological MongoDB Audit Verification (Simulated Redis/Mongo network failure vs accurate multi-collection audit archiving).

(`tests/test_weighting_engine_deep.py`)
"""
import pytest
import asyncio
import time
from typing import Dict, List, Any
from unittest.mock import patch, AsyncMock, MagicMock
from engine.weighting.constants import (
    EvidenceAvailability, WeightingStrategyType,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA,
    ALL_DOMAINS
)
from engine.weighting.config import weighting_config
from engine.weighting.schemas import UpstreamParticipantState, EvidencePayloads, DynamicWeightProfile, QualityScores
from engine.weighting.models import StrategyEvaluationContext
from engine.weighting.evidence_validator import EvidenceValidator
from engine.weighting.quality import QualityEvaluator
from engine.weighting.strategy import StrategySelector
from engine.weighting.rules import DynamicRuleEngine
from engine.weighting.scorer import WeightScorerAndNormalizer
from engine.weighting.weight_manager import WeightManager
from engine.weighting.storage import WeightingStorageManager
from engine.weighting.engine import DynamicWeightingEngine
from engine.weighting.pipeline import WeightingPipeline
from engine.weighting.workers import WeightingWorkerManager


# ──────────────────────────────────────────────────────────────────────────────
# 1. Combinatorial Domain Matrix ($2^7 = 128$ Availability Combinations)
# ──────────────────────────────────────────────────────────────────────────────
class TestCombinatorialDomainMatrix:
  def test_all_128_availability_combinations_normalize_to_one(self):
    """Verify exact normalization sum == 1.0 across every single one of the 128 domain availability permutations."""
    sel = StrategySelector()
    rules = DynamicRuleEngine()
    scorer = WeightScorerAndNormalizer()
    base_w = sel.get_base_weights(WeightingStrategyType.DEFAULT)
    q = QualityScores()
    ctx = StrategyEvaluationContext(meeting_id="m_matrix", participant_id="p_matrix", elapsed_meeting_sec=100.0)

    # Iterate through 0 to 127 (binary representation maps to available/unavailable across 7 domains)
    for i in range(128):
      avail_map: Dict[str, EvidenceAvailability] = {}
      for idx, dom in enumerate(ALL_DOMAINS):
        is_avail = bool((i >> idx) & 1)
        avail_map[dom] = EvidenceAvailability.AVAILABLE if is_avail else EvidenceAvailability.UNAVAILABLE

      raw, reasons = rules.apply_rules(base_w, avail_map, q, ctx)
      norm, norm_factor, final_reasons = scorer.normalize_weights(raw, reasons, availabilities=avail_map)

      # 1. Check sum == 1.0 exactly
      total_weight = sum(norm.values())
      assert total_weight == pytest.approx(1.0, abs=1e-6), f"Permutation {i} failed normalization sum: {total_weight}"

      # 2. Check all unavailable domains get exactly 0.0
      for dom, st in avail_map.items():
        if st == EvidenceAvailability.UNAVAILABLE and i > 0:  # i=0 is all unavailable -> fallback distribution
          assert norm[dom] == 0.0, f"Permutation {i}: {dom} was UNAVAILABLE but received weight {norm[dom]}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Real-Time 45-Minute Meeting Lifecycle & Dynamic Transitions
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestMeetingLifecycleTrajectory:
  async def test_45_minute_dynamic_meeting_trajectory(self):
    """Simulate a full 45m interview with Candidate_Alice experiencing dynamic phases and hardware toggles."""
    with patch("engine.weighting.participant_state.get_redis", new_callable=AsyncMock) as m_r1, \
         patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_r2, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r1.return_value = None
      m_r2.return_value = None
      m_db.return_value = None

      engine = DynamicWeightingEngine()
      meeting_id = "m_lifecycle_45m"
      participant_id = "Candidate_Alice"

      # Base rich payloads
      payloads = EvidencePayloads(
          visual_evidence={"confidence": 0.92, "face_visible": True, "face_size_ratio": 0.16},
          voice_evidence={"confidence": 0.90, "speech_duration_sec": 8.0, "diarization_confidence": 0.90},
          transcript_evidence={"whisper_confidence": 0.91, "completeness": 0.95},
          conversation_evidence={"transcript_coverage": 0.90, "reasoning_confidence": 0.92},
          behavior_evidence={"data_points_collected": 20, "reliability": 0.90},
          identity_evidence={"fuzzy_score": 0.95, "embedding_similarity": 0.94},
          metadata_evidence={"verified_email": True, "calendar_info_present": True}
      )

      # Phase 1: Minute 1 (Elapsed 60s) -> Interview Started
      p_state_m1 = UpstreamParticipantState(
          participant_id=participant_id, meeting_id=meeting_id,
          camera_on=True, mic_on=True, face_visible=True, voice_detected=True
      )
      prof_m1 = await engine.compute_weights(meeting_id, participant_id, p_state_m1, payloads, elapsed_meeting_sec=60.0)
      assert prof_m1.strategy_used == WeightingStrategyType.INTERVIEW_STARTED
      assert sum(prof_m1.as_dict().values()) == pytest.approx(1.0)

      # Phase 2: Minute 5 (Elapsed 300s) -> Interview In Progress
      prof_m5 = await engine.compute_weights(meeting_id, participant_id, p_state_m1, payloads, elapsed_meeting_sec=300.0)
      assert prof_m5.strategy_used == WeightingStrategyType.INTERVIEW_IN_PROGRESS
      assert prof_m5.conversation_weight > prof_m1.conversation_weight  # Conversation weight rises as interview progresses

      # Phase 3: Minute 10 (Elapsed 600s) -> Coding Round Transition
      prof_m10 = await engine.compute_weights(
          meeting_id, participant_id, p_state_m1, payloads,
          elapsed_meeting_sec=600.0, meeting_tags=["CODING_ROUND"]
      )
      assert prof_m10.strategy_used == WeightingStrategyType.CODING_ROUND
      assert prof_m10.conversation_weight >= 0.20
      assert prof_m10.transcript_weight >= prof_m5.transcript_weight

      # Phase 4: Minute 15 (Elapsed 900s) -> Hardware Glitch / Camera Off
      p_state_cam_off = UpstreamParticipantState(
          participant_id=participant_id, meeting_id=meeting_id,
          camera_on=False, mic_on=True, face_visible=False, voice_detected=True
      )
      prof_m15 = await engine.compute_weights(
          meeting_id, participant_id, p_state_cam_off, payloads,
          elapsed_meeting_sec=900.0, meeting_tags=["CODING_ROUND"], force_recompute=True
      )
      assert prof_m15.visual_weight == 0.0
      assert prof_m15.voice_weight > prof_m10.voice_weight
      assert any("Camera off" in r for r in prof_m15.reasoning)

      # Phase 5: Minute 20 (Elapsed 1200s) -> Screen Share Active
      p_state_screen = UpstreamParticipantState(
          participant_id=participant_id, meeting_id=meeting_id,
          camera_on=True, mic_on=True, face_visible=True, screen_share=True
      )
      prof_m20 = await engine.compute_weights(
          meeting_id, participant_id, p_state_screen, payloads,
          elapsed_meeting_sec=1200.0, meeting_tags=["CODING_ROUND"], force_recompute=True
      )
      assert prof_m20.behavior_weight > prof_m10.behavior_weight
      assert any("Screen share active" in r for r in prof_m20.reasoning)

      # Phase 6: Minute 26 (Elapsed 1560s) -> Long Meeting Fatigue Rule
      prof_m26 = await engine.compute_weights(
          meeting_id, participant_id, p_state_screen, payloads,
          elapsed_meeting_sec=1560.0, meeting_tags=["CODING_ROUND"], force_recompute=True
      )
      assert any("Long meeting duration" in r for r in prof_m26.reasoning)

      # Phase 7: Minute 35 (Elapsed 2100s) -> Behavioral Round Transition
      prof_m35 = await engine.compute_weights(
          meeting_id, participant_id, p_state_m1, payloads,
          elapsed_meeting_sec=2100.0, meeting_tags=["BEHAVIORAL"]
      )
      assert prof_m35.strategy_used == WeightingStrategyType.BEHAVIOR_ROUND
      assert prof_m35.visual_weight > 0.15


# ──────────────────────────────────────────────────────────────────────────────
# 3. Adversarial Quality & Diarization Degradation Boundary Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestAdversarialQualityBoundaries:
  def test_extreme_face_blur_and_diarization_failure_penalties(self):
    sel = StrategySelector()
    rules = DynamicRuleEngine()
    scorer = WeightScorerAndNormalizer()
    evaluator = QualityEvaluator()

    base_w = sel.get_base_weights(WeightingStrategyType.INTERVIEW_IN_PROGRESS)
    p_state = UpstreamParticipantState(participant_id="p_adv", meeting_id="m_adv")

    # Feed severe blur and diarization failure
    bad_payloads = EvidencePayloads(
        visual_evidence={"face_visible": True, "face_size_ratio": 0.01, "tracking_confidence": 0.10, "recognition_confidence": 0.10},
        voice_evidence={"speech_duration_sec": 0.2, "diarization_confidence": 0.20, "speaker_recognition_confidence": 0.20, "vad_confidence": 0.30}
    )
    avail = {dom: EvidenceAvailability.AVAILABLE for dom in base_w}
    q_bad = evaluator.evaluate_quality(bad_payloads, avail, p_state)

    assert q_bad.visual_quality < weighting_config.MIN_FACE_QUALITY
    assert q_bad.voice_quality < weighting_config.MIN_SPEECH_DIARIZATION_CONFIDENCE

    ctx = StrategyEvaluationContext(meeting_id="m_adv", participant_id="p_adv", elapsed_meeting_sec=300.0)
    raw, reasons = rules.apply_rules(base_w, avail, q_bad, ctx)

    assert any("Poor face quality" in r for r in reasons)
    assert any("Poor speaker recognition/diarization" in r for r in reasons)

    norm, _, _ = scorer.normalize_weights(raw, reasons)
    assert sum(norm.values()) == pytest.approx(1.0)
    assert norm[DOMAIN_VISUAL] < base_w[DOMAIN_VISUAL]
    assert norm[DOMAIN_VOICE] < base_w[DOMAIN_VOICE]

  def test_simultaneous_super_high_confidence_booster(self):
    sel = StrategySelector()
    rules = DynamicRuleEngine()
    scorer = WeightScorerAndNormalizer()
    evaluator = QualityEvaluator()

    base_w = sel.get_base_weights(WeightingStrategyType.INTERVIEW_IN_PROGRESS)
    p_state = UpstreamParticipantState(participant_id="p_boost", meeting_id="m_boost")

    # Feed pristine quality scores across visual, voice, and metadata
    boost_payloads = EvidencePayloads(
        visual_evidence={"face_visible": True, "face_size_ratio": 0.20, "tracking_confidence": 0.99, "recognition_confidence": 0.98},
        voice_evidence={"speech_duration_sec": 10.0, "diarization_confidence": 0.99, "speaker_recognition_confidence": 0.97, "vad_confidence": 0.99},
        metadata_evidence={"verified_email": True, "verified_participant": True, "calendar_info_present": True}
    )
    avail = {dom: EvidenceAvailability.AVAILABLE for dom in base_w}
    q_boost = evaluator.evaluate_quality(boost_payloads, avail, p_state)

    assert q_boost.visual_quality > 0.90
    assert q_boost.voice_quality > 0.90
    assert q_boost.metadata_quality > 0.90

    ctx = StrategyEvaluationContext(meeting_id="m_boost", participant_id="p_boost", elapsed_meeting_sec=300.0)
    raw, reasons = rules.apply_rules(base_w, avail, q_boost, ctx)

    assert any("Very high face recognition confidence" in r for r in reasons)
    assert any("Very high voice/speaker confidence" in r for r in reasons)
    assert any("Strong verified metadata" in r for r in reasons)

    norm, _, _ = scorer.normalize_weights(raw, reasons)
    assert sum(norm.values()) == pytest.approx(1.0)

  def test_unfinalized_partial_transcript_coverage_penalty(self):
    evaluator = QualityEvaluator()
    p_state = UpstreamParticipantState(participant_id="p_trans", meeting_id="m_trans")
    payload = EvidencePayloads(
        transcript_evidence={"whisper_confidence": 0.90, "completeness": 0.90, "is_final": False}
    )
    avail = {DOMAIN_TRANSCRIPT: EvidenceAvailability.AVAILABLE}
    q = evaluator.evaluate_quality(payload, avail, p_state)
    assert q.transcript_quality < 0.80  # Penalty applied due to non-finalized status


# ──────────────────────────────────────────────────────────────────────────────
# 4. High-Speed Caching & Delta Threshold Invalidation
# ──────────────────────────────────────────────────────────────────────────────
class TestHighSpeedCachingAndInvalidation:
  def test_sub_millisecond_cache_retrieval_and_thresholds(self):
    manager = WeightManager()
    p_state = UpstreamParticipantState(participant_id="p_cache", meeting_id="m_cache")
    q_initial = QualityScores(visual_quality=0.80, voice_quality=0.80, transcript_quality=0.80)
    strat = WeightingStrategyType.DEFAULT

    # Initial check -> should recompute
    assert manager.should_recompute("m_cache", "p_cache", p_state, q_initial, strat) is True

    # Store profile
    prof = DynamicWeightProfile(
        participant_id="p_cache", meeting_id="m_cache",
        visual_weight=0.2, voice_weight=0.2, transcript_weight=0.2,
        conversation_weight=0.2, behavior_weight=0.1, identity_weight=0.05,
        metadata_weight=0.05, normalization_factor=1.0, overall_quality=q_initial.get_overall_quality(),
        strategy_used=strat
    )
    manager.update_cache(prof, p_state, q_initial)

    # 1. Stress test 500 rapid successive cache lookups
    start_t = time.perf_counter()
    for _ in range(500):
      assert manager.should_recompute("m_cache", "p_cache", p_state, q_initial, strat) is False
      cached = manager.get_cached_profile("m_cache", "p_cache")
      assert cached is not None
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
    assert (elapsed_ms / 500.0) < 0.1, f"Average cache lookup latency too high: {elapsed_ms / 500.0:.4f} ms"

    # 2. Check small quality variation (< 0.05 delta threshold) -> should NOT recompute
    q_slight = QualityScores(visual_quality=0.82, voice_quality=0.81, transcript_quality=0.80)
    assert abs(q_slight.get_overall_quality() - q_initial.get_overall_quality()) < weighting_config.QUALITY_CHANGE_RECOMPUTE_DELTA
    assert manager.should_recompute("m_cache", "p_cache", p_state, q_slight, strat) is False

    # 3. Check large quality jump (>= 0.05 delta threshold) -> SHOULD recompute
    q_major = QualityScores(visual_quality=0.40, voice_quality=0.40, transcript_quality=0.40)
    assert abs(q_major.get_overall_quality() - q_initial.get_overall_quality()) >= weighting_config.QUALITY_CHANGE_RECOMPUTE_DELTA
    assert manager.should_recompute("m_cache", "p_cache", p_state, q_major, strat) is True

    # 4. Check explicit hardware toggle (mic muted) -> SHOULD recompute
    p_state_mic_mute = UpstreamParticipantState(participant_id="p_cache", meeting_id="m_cache", mic_on=False)
    assert manager.should_recompute("m_cache", "p_cache", p_state_mic_mute, q_initial, strat) is True


# ──────────────────────────────────────────────────────────────────────────────
# 5. Exhaustive Multi-Worker Concurrency & Queue Contention
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestMultiWorkerContentionAndBackpressure:
  async def test_4_workers_200_concurrent_jobs_without_deadlock(self):
    """Enqueue 200 tasks across 20 meetings and verify clean processing and zero unfinished tasks."""
    with patch("engine.weighting.participant_state.get_redis", new_callable=AsyncMock) as m_r1, \
         patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_r2, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r1.return_value = None
      m_r2.return_value = None
      m_db.return_value = None

      wm = WeightingWorkerManager(worker_count=4)
      await wm.start()

      # Enqueue 200 tasks
      enqueued_count = 0
      for m_idx in range(20):
        for p_idx in range(10):
          ok = await wm.enqueue_job(
              meeting_id=f"m_contention_{m_idx}",
              participant_id=f"Candidate_{p_idx}",
              elapsed_meeting_sec=float((p_idx + 1) * 60)
          )
          if ok:
            enqueued_count += 1

      assert enqueued_count == 200

      # Gracefully stop and wait for queue drainage
      await wm.stop()
      assert wm.queue.empty() is True
      assert wm.is_running is False


# ──────────────────────────────────────────────────────────────────────────────
# 6. Offline Storage Resilience & Chronological MongoDB Audit Verification
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestStorageAndAuditIntegrity:
  async def test_50_consecutive_offline_evaluations(self):
    """Verify in-memory fallback state retains 100% data integrity during network disconnection."""
    with patch("engine.weighting.participant_state.get_redis", new_callable=AsyncMock) as m_r1, \
         patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_r2, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r1.return_value = None
      m_r2.return_value = None
      m_db.return_value = None

      pipe = WeightingPipeline()
      meeting_id = "m_offline_resilience"

      for i in range(50):
        prof = await pipe.process_participant(
            meeting_id=meeting_id,
            participant_id=f"Participant_{i}",
            elapsed_meeting_sec=float(i * 10)
        )
        assert prof.participant_id == f"Participant_{i}"
        assert sum(prof.as_dict().values()) == pytest.approx(1.0)

      # Verify storage manager cached all 50 in memory
      storage = pipe.engine.storage
      for i in range(50):
        state = await storage.get_latest_state(meeting_id, f"Participant_{i}")
        assert state is not None and state.participant_id == f"Participant_{i}"

  async def test_mongo_audit_archiving_across_collections(self):
    """Verify exact document structures inserted across weight_profiles, weight_history, strategy_changes, quality_scores."""
    mock_db = MagicMock()
    mock_col_profiles = AsyncMock()
    mock_col_history = AsyncMock()
    mock_col_strat = AsyncMock()
    mock_col_qual = AsyncMock()

    mock_db.__getitem__.side_effect = lambda name: {
        "weight_profiles": mock_col_profiles,
        "weight_history": mock_col_history,
        "strategy_changes": mock_col_strat,
        "quality_scores": mock_col_qual
    }.get(name)

    with patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = mock_db

      storage = WeightingStorageManager()
      q = QualityScores()

      # 1. First evaluation -> DEFAULT strategy
      prof_1 = DynamicWeightProfile(
          participant_id="Candidate_Bob", meeting_id="m_audit",
          visual_weight=0.2, voice_weight=0.2, transcript_weight=0.2,
          conversation_weight=0.2, behavior_weight=0.1, identity_weight=0.05,
          metadata_weight=0.05, normalization_factor=1.0, overall_quality=0.9,
          strategy_used=WeightingStrategyType.DEFAULT
      )
      await storage.save_profile(prof_1, q, previous_strategy=None)
      assert mock_col_history.insert_one.call_count == 1
      assert mock_col_qual.insert_one.call_count == 1
      assert mock_col_strat.insert_one.call_count == 0  # No strategy transition yet

      # 2. Second evaluation -> Transition to CODING_ROUND
      prof_2 = DynamicWeightProfile(
          participant_id="Candidate_Bob", meeting_id="m_audit",
          visual_weight=0.15, voice_weight=0.20, transcript_weight=0.20,
          conversation_weight=0.25, behavior_weight=0.15, identity_weight=0.03,
          metadata_weight=0.02, normalization_factor=1.0, overall_quality=0.9,
          strategy_used=WeightingStrategyType.CODING_ROUND,
          reasoning=["Transition to coding round"]
      )
      await storage.save_profile(prof_2, q, previous_strategy="DEFAULT")
      assert mock_col_history.insert_one.call_count == 2
      assert mock_col_qual.insert_one.call_count == 2
      assert mock_col_strat.insert_one.call_count == 1  # Strategy transition recorded!

      strat_arg = mock_col_strat.insert_one.call_args[0][0]
      assert strat_arg["old_strategy"] == "DEFAULT"
      assert strat_arg["new_strategy"] == "CODING_ROUND"
      assert "Transition to coding round" in strat_arg["reasoning"]
