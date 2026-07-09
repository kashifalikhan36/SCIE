"""
Comprehensive Unit & Integration Tests for the SCIE Dynamic Weighting Engine (`engine/weighting/`).

Tests all 19 modular components:
- Core validation, quality evaluation, and strategy selection across 7 domains
- Dynamic rules: Camera Off, Mic Muted, No Transcript, Long Meeting, Quality boundaries
- Exact normalization (sum(weights) == 1.0) and zero contribution for unavailable domains
- Performance caching via WeightManager
- Offline memory fallback resilience via WeightingStorageManager
- Orchestration via WeightingPipeline and async workers

(`tests/test_weighting_engine.py`)
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from engine.weighting.constants import (
    EvidenceAvailability, WeightingStrategyType,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
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
from engine.weighting.utils import clamp, safe_divide, calculate_time_decay


# ──────────────────────────────────────────────────────────────────────────────
# 1. Utils & Safe Math Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestWeightingUtils:
  def test_clamp_boundaries_and_special_values(self):
    assert clamp(0.5, 0.0, 1.0) == 0.5
    assert clamp(-0.5, 0.0, 1.0) == 0.0
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(float("nan"), 0.0, 1.0) == 0.0
    assert clamp(float("inf"), 0.0, 1.0) == 1.0
    assert clamp(float("-inf"), 0.0, 1.0) == 0.0

  def test_safe_divide(self):
    assert safe_divide(10.0, 2.0) == 5.0
    assert safe_divide(10.0, 0.0, default=0.0) == 0.0
    assert safe_divide(10.0, 1e-15, default=0.0) == 0.0

  def test_time_decay(self):
    assert calculate_time_decay(0.0, 60.0) == 1.0
    assert calculate_time_decay(60.0, 60.0) == 0.5
    assert calculate_time_decay(120.0, 60.0) == 0.25


# ──────────────────────────────────────────────────────────────────────────────
# 2. Evidence Availability & Quality Evaluation Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestAvailabilityAndQuality:
  def test_evidence_validator_camera_off_and_mic_muted(self):
    validator = EvidenceValidator()
    p_state = UpstreamParticipantState(
        participant_id="p1", meeting_id="m1",
        camera_on=False, mic_on=False, transcript_available=True
    )
    payloads = EvidencePayloads(
        visual_evidence={"confidence": 0.90},
        voice_evidence={"confidence": 0.90},
        transcript_evidence={"confidence": 0.90}
    )
    avail = validator.evaluate_availability(payloads, p_state)
    assert avail[DOMAIN_VISUAL] == EvidenceAvailability.UNAVAILABLE
    assert avail[DOMAIN_VOICE] == EvidenceAvailability.UNAVAILABLE
    assert avail[DOMAIN_TRANSCRIPT] == EvidenceAvailability.AVAILABLE

  def test_quality_evaluator_scores_and_degraded_penalty(self):
    evaluator = QualityEvaluator()
    p_state = UpstreamParticipantState(participant_id="p1", meeting_id="m1")
    payloads = EvidencePayloads(
        visual_evidence={"face_visible": True, "face_size_ratio": 0.15, "tracking_confidence": 0.9, "recognition_confidence": 0.9},
        voice_evidence={"speech_duration_sec": 5.0, "diarization_confidence": 0.9, "speaker_recognition_confidence": 0.9, "vad_confidence": 0.9}
    )
    avail = {
        DOMAIN_VISUAL: EvidenceAvailability.AVAILABLE,
        DOMAIN_VOICE: EvidenceAvailability.DEGRADED,
        DOMAIN_TRANSCRIPT: EvidenceAvailability.AVAILABLE
    }
    q = evaluator.evaluate_quality(payloads, avail, p_state)
    assert q.visual_quality > 0.85
    assert q.voice_quality < q.visual_quality  # Degraded penalty (* 0.6) applied


# ──────────────────────────────────────────────────────────────────────────────
# 3. Strategy Selection & Pluggable Registry Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestStrategySelector:
  def test_strategy_selection_tags_and_stages(self):
    sel = StrategySelector()
    ctx_start = StrategyEvaluationContext(meeting_id="m1", participant_id="p1", elapsed_meeting_sec=60.0)
    assert sel.select_strategy(ctx_start) == WeightingStrategyType.INTERVIEW_STARTED

    ctx_coding = StrategyEvaluationContext(meeting_id="m1", participant_id="p1", elapsed_meeting_sec=600.0, meeting_tags=["CODING_ROUND"])
    assert sel.select_strategy(ctx_coding) == WeightingStrategyType.CODING_ROUND

    ctx_cam_off = StrategyEvaluationContext(meeting_id="m1", participant_id="p1", elapsed_meeting_sec=300.0, camera_on=False)
    assert sel.select_strategy(ctx_cam_off) == WeightingStrategyType.CAMERA_OFF

  def test_custom_strategy_registry(self):
    sel = StrategySelector()
    custom_type = WeightingStrategyType("DEFAULT")  # overwrite for test
    custom_weights = {dom: 1.0 / 7.0 for dom in (DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT, DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA)}
    sel.register_strategy(custom_type, custom_weights)
    assert sel.get_base_weights(custom_type)[DOMAIN_VISUAL] == pytest.approx(1.0 / 7.0)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Dynamic Rules & Exact Weight Normalization Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestRulesAndScoring:
  def test_camera_off_rule_and_exact_normalization(self):
    sel = StrategySelector()
    rules = DynamicRuleEngine()
    scorer = WeightScorerAndNormalizer()

    base_w = sel.get_base_weights(WeightingStrategyType.CAMERA_OFF)
    avail = {
        DOMAIN_VISUAL: EvidenceAvailability.UNAVAILABLE,
        DOMAIN_VOICE: EvidenceAvailability.AVAILABLE,
        DOMAIN_TRANSCRIPT: EvidenceAvailability.AVAILABLE,
        DOMAIN_CONVERSATION: EvidenceAvailability.AVAILABLE,
        DOMAIN_BEHAVIOR: EvidenceAvailability.AVAILABLE,
        DOMAIN_IDENTITY: EvidenceAvailability.AVAILABLE,
        DOMAIN_METADATA: EvidenceAvailability.AVAILABLE,
    }
    q = QualityScores()
    ctx = StrategyEvaluationContext(meeting_id="m1", participant_id="p1", elapsed_meeting_sec=300.0, camera_on=False)

    raw, reasons = rules.apply_rules(base_w, avail, q, ctx)
    assert raw[DOMAIN_VISUAL] == 0.0
    assert any("Camera off" in r or "Visual weight set to 0.0" in r for r in reasons)

    norm, factor, final_reasons = scorer.normalize_weights(raw, reasons)
    assert norm[DOMAIN_VISUAL] == 0.0
    assert sum(norm.values()) == pytest.approx(1.0)

  def test_no_transcript_and_long_meeting_rules(self):
    sel = StrategySelector()
    rules = DynamicRuleEngine()
    scorer = WeightScorerAndNormalizer()

    base_w = sel.get_base_weights(WeightingStrategyType.DEFAULT)
    avail = {dom: EvidenceAvailability.AVAILABLE for dom in base_w}
    avail[DOMAIN_TRANSCRIPT] = EvidenceAvailability.UNAVAILABLE
    q = QualityScores()
    ctx = StrategyEvaluationContext(
        meeting_id="m1", participant_id="p1", elapsed_meeting_sec=1200.0,  # 20m (>15m long meeting)
        transcript_available=False
    )

    raw, reasons = rules.apply_rules(base_w, avail, q, ctx)
    assert raw[DOMAIN_TRANSCRIPT] == 0.0
    assert raw[DOMAIN_CONVERSATION] == 0.0
    assert any("No transcript available" in r for r in reasons)
    assert any("Long meeting duration" in r for r in reasons)

    norm, factor, _ = scorer.normalize_weights(raw, reasons)
    assert norm[DOMAIN_TRANSCRIPT] == 0.0
    assert norm[DOMAIN_CONVERSATION] == 0.0
    assert sum(norm.values()) == pytest.approx(1.0)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Calculation Caching & Storage Resilience Tests
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestCachingAndStorageResilience:
  async def test_weight_manager_caching_skips_unnecessary_recompute(self):
    manager = WeightManager()
    p_state = UpstreamParticipantState(participant_id="p1", meeting_id="m1")
    q = QualityScores()
    strat = WeightingStrategyType.DEFAULT

    assert manager.should_recompute("m1", "p1", p_state, q, strat) is True

    # Store profile
    dummy_prof = DynamicWeightProfile(
        participant_id="p1", meeting_id="m1",
        visual_weight=0.2, voice_weight=0.2, transcript_weight=0.2,
        conversation_weight=0.2, behavior_weight=0.1, identity_weight=0.05,
        metadata_weight=0.05, normalization_factor=1.0, overall_quality=0.9,
        strategy_used=strat
    )
    manager.update_cache(dummy_prof, p_state, q)

    # Should not recompute when exact same state and quality arrive
    assert manager.should_recompute("m1", "p1", p_state, q, strat) is False

    # Toggle camera off -> should trigger recompute
    p_state_cam_off = UpstreamParticipantState(participant_id="p1", meeting_id="m1", camera_on=False)
    assert manager.should_recompute("m1", "p1", p_state_cam_off, q, strat) is True

  async def test_storage_manager_offline_memory_resilience(self):
    storage = WeightingStorageManager()
    with patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_mongo:
      m_redis.return_value = None
      m_mongo.return_value = None

      dummy_prof = DynamicWeightProfile(
          participant_id="p_off", meeting_id="m_off",
          visual_weight=0.2, voice_weight=0.2, transcript_weight=0.2,
          conversation_weight=0.2, behavior_weight=0.1, identity_weight=0.05,
          metadata_weight=0.05, normalization_factor=1.0, overall_quality=0.9
      )
      q = QualityScores()

      saved = await storage.save_profile(dummy_prof, q)
      assert saved.participant_id == "p_off"

      cached = await storage.get_latest_state("m_off", "p_off")
      assert cached is not None and cached.participant_id == "p_off"


# ──────────────────────────────────────────────────────────────────────────────
# 6. End-to-End Pipeline & Background Worker Pool Tests
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestPipelineAndWorkers:
  async def test_end_to_end_weighting_pipeline(self):
    with patch("engine.weighting.participant_state.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_s_redis, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_redis.return_value = None
      m_s_redis.return_value = None
      m_db.return_value = None

      pipe = WeightingPipeline()
      payloads = EvidencePayloads(
          visual_evidence={"confidence": 0.95, "face_visible": True},
          voice_evidence={"confidence": 0.90, "speech_duration_sec": 4.0}
      )

      profile = await pipe.process_participant(
          meeting_id="m_live",
          participant_id="Candidate_John",
          payloads=payloads,
          elapsed_meeting_sec=400.0,
          meeting_tags=["CODING_ROUND"]
      )
      assert profile is not None
      assert profile.participant_id == "Candidate_John"
      assert profile.strategy_used == WeightingStrategyType.CODING_ROUND
      assert sum([
          profile.visual_weight, profile.voice_weight, profile.transcript_weight,
          profile.conversation_weight, profile.behavior_weight, profile.identity_weight,
          profile.metadata_weight
      ]) == pytest.approx(1.0)

  async def test_worker_manager_concurrency_drainage(self):
    with patch("engine.weighting.participant_state.get_redis", new_callable=AsyncMock) as m_r1, \
         patch("engine.weighting.storage.get_redis", new_callable=AsyncMock) as m_r2, \
         patch("engine.weighting.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r1.return_value = None
      m_r2.return_value = None
      m_db.return_value = None

      wm = WeightingWorkerManager(worker_count=2)
      await wm.start()

      for i in range(10):
        ok = await wm.enqueue_job(
            meeting_id="m_workers",
            participant_id=f"p_{i}",
            elapsed_meeting_sec=float(i * 10)
        )
        assert ok is True

      await wm.stop()
      assert wm.queue.empty() is True
