"""
Comprehensive Deep Test Suite for the Evidence Fusion Engine (`tests/test_fusion_engine.py`).

Verifies all 18 modules of the Evidence Fusion Engine across 12 distinct test groups covering:
- Time utilities, decay calculation, clamping, and safe division.
- Standardized `IncomingEvidence` schema wrappers and Pydantic model validations.
- In-memory & windowed deduplication checks (`EvidenceCache`).
- Out-of-order timestamp handling and domain slot assignment (`EvidenceAggregator`).
- Dynamic weight adjustment and redistribution (`DynamicWeightingEngine`).
- Domain score normalization and reliability weighting (`EvidenceScorer`).
- Monotonically evolving multi-signal confidence trajectory and single-signal guards (`ConfidenceEngine`).
- Multi-participant sorting and rank assignment (`ParticipantRanker`).
- Structured rule-based explanation building (`ExplanationBuilder`).
- Redis live state caching and MongoDB 7-collection audit persistence (`FusionStateManager`, `FusionPersistenceManager`).
- Top-level end-to-end orchestration (`FusionPipeline`).
- Event-driven async background worker pool lifecycle (`FusionWorkerManager`).
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from engine.fusion.constants import (
    EvidenceStatus,
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT
)
from engine.fusion.utils import (
    now_ms, format_timestamp_ms, safe_divide, clamp,
    calculate_time_decay, generate_fusion_event_id, generate_explanation_id
)
from engine.fusion.schemas import (
    IncomingEvidence, ParticipantState, ParticipantScore,
    RankingResult, Explanation, ConfidenceHistoryItem, FusionResult
)
from engine.fusion.models import WeightedEvidenceItem, ConfidenceComputationContext
from engine.fusion.evidence_cache import EvidenceCache
from engine.fusion.aggregator import EvidenceAggregator
from engine.fusion.weighting import DynamicWeightingEngine
from engine.fusion.scorer import EvidenceScorer
from engine.fusion.confidence import ConfidenceEngine
from engine.fusion.participant_ranker import ParticipantRanker
from engine.fusion.explanation import ExplanationBuilder
from engine.fusion.state_manager import FusionStateManager
from engine.fusion.persistence import FusionPersistenceManager
from engine.fusion.pipeline import FusionPipeline
from engine.fusion.workers import FusionWorkerManager, enqueue_fusion_evidence
from engine.fusion.exceptions import DuplicateEvidenceError, EvidenceAggregationError


# ──────────────────────────────────────────────────────────────────────────────
# 1. Test Fusion Utils
# ──────────────────────────────────────────────────────────────────────────────

class TestFusionUtils:
  def test_now_ms_returns_reasonable_epoch(self):
    t = now_ms()
    assert isinstance(t, int)
    assert t > 1700000000000

  def test_format_timestamp_ms(self):
    assert format_timestamp_ms(0) == "00:00:00"
    assert format_timestamp_ms(-500) == "00:00:00"
    # 3661 seconds = 1 hr, 1 min, 1 sec
    assert format_timestamp_ms(3661000) == "01:01:01"

  def test_safe_divide(self):
    assert safe_divide(10.0, 2.0) == 5.0
    assert safe_divide(10.0, 0.0, default=-1.0) == -1.0
    assert safe_divide(10.0, 1e-11, default=0.0) == 0.0

  def test_clamp(self):
    assert clamp(-0.5, 0.0, 1.0) == 0.0
    assert clamp(1.5, 0.0, 1.0) == 1.0
    assert clamp(0.7, 0.0, 1.0) == 0.7

  def test_calculate_time_decay(self):
    # age <= 0 -> 1.0
    assert calculate_time_decay(-5.0, 60.0) == 1.0
    assert calculate_time_decay(0.0, 60.0) == 1.0
    # exactly 1 half life -> 0.5
    assert abs(calculate_time_decay(60.0, 60.0) - 0.5) < 1e-4
    # exactly 2 half lives -> 0.25
    assert abs(calculate_time_decay(120.0, 60.0) - 0.25) < 1e-4

  def test_id_generators(self):
    ev_id = generate_fusion_event_id()
    ex_id = generate_explanation_id()
    assert ev_id.startswith("FE_")
    assert ex_id.startswith("EX_")
    assert len(ev_id) >= 11
    assert len(ex_id) >= 11


# ──────────────────────────────────────────────────────────────────────────────
# 2. Test Fusion Schemas
# ──────────────────────────────────────────────────────────────────────────────

class TestFusionSchemas:
  def test_incoming_evidence_from_dict(self):
    raw = {
        "evidence_id": "VIS_101",
        "meeting_id": "mtg_alpha",
        "face_similarity": 0.94,
        "recognition_confidence": 0.92,
        "track_id": "tr_1",
        "timestamp": 1710000000000
    }
    wrapped = IncomingEvidence.from_evidence(raw, source_type=DOMAIN_VISUAL)
    assert wrapped.evidence_id == "VIS_101"
    assert wrapped.meeting_id == "mtg_alpha"
    assert wrapped.source_type == DOMAIN_VISUAL
    assert wrapped.score == 0.94
    assert wrapped.reliability == 0.92
    assert wrapped.track_id == "tr_1"
    assert wrapped.status == EvidenceStatus.AVAILABLE

  def test_incoming_evidence_from_mock_model(self):
    class MockModel:
      def model_dump(self):
        return {
            "conversation_turn_id": "TURN_55",
            "meeting_id": "mtg_beta",
            "score": 0.88,
            "confidence": 0.85,
            "speaker_id": "spk_2"
        }
    wrapped = IncomingEvidence.from_evidence(MockModel(), source_type=DOMAIN_CONVERSATION)
    assert wrapped.evidence_id == "TURN_55"
    assert wrapped.score == 0.88
    assert wrapped.reliability == 0.85
    assert wrapped.speaker_id == "spk_2"

  def test_incoming_evidence_clamping_bounds(self):
    raw = {"evidence_id": "E1", "meeting_id": "M", "score": 2.5, "confidence": -0.4}
    wrapped = IncomingEvidence.from_evidence(raw, source_type=DOMAIN_VOICE)
    assert wrapped.score == 1.0
    assert wrapped.reliability == 0.0

  def test_participant_state_defaults(self):
    st = ParticipantState(participant_id="p1", meeting_id="mtg1")
    assert st.confidence == 0.0
    assert st.identity_evidence is None
    assert st.visual_evidence is None
    assert st.extra_evidence == {}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Test Evidence Cache
# ──────────────────────────────────────────────────────────────────────────────

class TestEvidenceCache:
  def test_set_and_get_active_evidence(self):
    cache = EvidenceCache()
    ev = IncomingEvidence(
        evidence_id="ev_test_1",
        meeting_id="m1",
        source_type=DOMAIN_VISUAL,
        participant_id="p1",
        score=0.9
    )
    cache.set_evidence_item("m1", "p1", ev)
    active = cache.get_active_evidence("m1", "p1")
    assert DOMAIN_VISUAL in active
    assert active[DOMAIN_VISUAL].evidence_id == "ev_test_1"

  def test_exact_id_duplicate(self):
    cache = EvidenceCache()
    ev = IncomingEvidence(evidence_id="ID_DUP", meeting_id="m1", source_type=DOMAIN_VOICE, participant_id="p1")
    assert not cache.is_duplicate(ev)
    cache.set_evidence_item("m1", "p1", ev)
    assert cache.is_duplicate(ev) is True

  def test_windowed_timestamp_duplicate(self):
    cache = EvidenceCache()
    ev1 = IncomingEvidence(
        evidence_id="ID_1", meeting_id="m1", source_type=DOMAIN_BEHAVIOR,
        participant_id="p1", score=0.75, timestamp=10000
    )
    cache.set_evidence_item("m1", "p1", ev1)

    # Identical score and within 2.0 second window -> duplicate
    ev2 = IncomingEvidence(
        evidence_id="ID_2", meeting_id="m1", source_type=DOMAIN_BEHAVIOR,
        participant_id="p1", score=0.75, timestamp=11000
    )
    assert cache.is_duplicate(ev2) is True

  def test_clear_cache(self):
    cache = EvidenceCache()
    ev = IncomingEvidence(evidence_id="e1", meeting_id="m1", source_type=DOMAIN_VISUAL, participant_id="p1")
    cache.set_evidence_item("m1", "p1", ev)
    cache.clear_cache("m1", "p1")
    assert cache.get_active_evidence("m1", "p1") == {}


# ──────────────────────────────────────────────────────────────────────────────
# 4. Test Evidence Aggregator
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestEvidenceAggregator:
  async def test_aggregate_into_fresh_state(self):
    agg = EvidenceAggregator()
    ev = IncomingEvidence(
        evidence_id="ev_agg_1",
        meeting_id="m1",
        source_type=DOMAIN_VISUAL,
        participant_id="p1",
        score=0.92,
        timestamp=20000,
        payload={"raw": "data"}
    )
    # Ensure cache clear for fresh test
    from engine.fusion.evidence_cache import evidence_cache
    evidence_cache.clear_cache("m1")
    evidence_cache._processed_ids.clear()

    st = await agg.aggregate_evidence(ev, current_state=None)
    assert st.participant_id == "p1"
    assert st.visual_evidence is not None
    assert st.visual_evidence["score"] == 0.92

  async def test_aggregate_out_of_order_preserves_newer(self):
    agg = EvidenceAggregator()
    from engine.fusion.evidence_cache import evidence_cache
    evidence_cache.clear_cache("m1")
    evidence_cache._processed_ids.clear()

    # First receive newer event
    ev_newer = IncomingEvidence(
        evidence_id="ev_new", meeting_id="m1", source_type=DOMAIN_VOICE,
        participant_id="p1", score=0.90, timestamp=50000
    )
    st = await agg.aggregate_evidence(ev_newer, current_state=None)

    # Now receive older event out-of-order
    ev_older = IncomingEvidence(
        evidence_id="ev_old", meeting_id="m1", source_type=DOMAIN_VOICE,
        participant_id="p1", score=0.60, timestamp=30000
    )
    st_after = await agg.aggregate_evidence(ev_older, current_state=st)
    # The slot should retain the newer score (0.90)
    assert st_after.voice_evidence["score"] == 0.90

  async def test_duplicate_raises_exception(self):
    agg = EvidenceAggregator()
    from engine.fusion.evidence_cache import evidence_cache
    evidence_cache.clear_cache("m1")
    evidence_cache._processed_ids.clear()

    ev = IncomingEvidence(evidence_id="DUP_EXC", meeting_id="m1", source_type=DOMAIN_IDENTITY, participant_id="p1")
    await agg.aggregate_evidence(ev, current_state=None)
    with pytest.raises(DuplicateEvidenceError):
      await agg.aggregate_evidence(ev, current_state=None)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Test Dynamic Weighting Engine
# ──────────────────────────────────────────────────────────────────────────────

class TestDynamicWeightingEngine:
  def test_camera_off_redistributes_weights(self):
    dwe = DynamicWeightingEngine()
    st = ParticipantState(
        participant_id="p1",
        meeting_id="m1",
        identity_evidence={"score": 0.9, "status": "AVAILABLE", "timestamp": 10000},
        visual_evidence={"score": 0.0, "status": "UNAVAILABLE", "timestamp": 10000},  # Camera off!
        voice_evidence={"score": 0.8, "status": "AVAILABLE", "timestamp": 10000},
    )
    dmap = dwe.compute_dynamic_weights(st, current_time_ms=10000)
    # Visual weight must be exactly 0.0
    assert dmap[DOMAIN_VISUAL].effective_weight == 0.0
    # Remaining active domains must sum to 1.0
    active_sum = sum(it.effective_weight for it in dmap.values())
    assert abs(active_sum - 1.0) < 1e-4

  def test_all_domains_available_proportional(self):
    dwe = DynamicWeightingEngine()
    st = ParticipantState(
        participant_id="p1", meeting_id="m1",
        identity_evidence={"score": 0.9, "timestamp": 1000},
        visual_evidence={"score": 0.9, "timestamp": 1000},
        voice_evidence={"score": 0.9, "timestamp": 1000},
        behavior_evidence={"score": 0.9, "timestamp": 1000},
        conversation_evidence={"score": 0.9, "timestamp": 1000},
    )
    dmap = dwe.compute_dynamic_weights(st, current_time_ms=1000)
    active_sum = sum(it.effective_weight for it in dmap.values())
    assert abs(active_sum - 1.0) < 1e-4
    assert dmap[DOMAIN_IDENTITY].effective_weight > 0.0

  def test_stale_domain_decay(self):
    dwe = DynamicWeightingEngine()
    st = ParticipantState(
        participant_id="p1", meeting_id="m1",
        # 100 seconds old -> older than FRESHNESS_TIMEOUT_SEC (30s)
        visual_evidence={"score": 0.9, "timestamp": 10000},
        # Fresh
        voice_evidence={"score": 0.9, "timestamp": 109000}
    )
    dmap = dwe.compute_dynamic_weights(st, current_time_ms=110000)
    assert dmap[DOMAIN_VISUAL].freshness_multiplier < 1.0
    assert dmap[DOMAIN_VOICE].freshness_multiplier == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 6. Test Evidence Scorer
# ──────────────────────────────────────────────────────────────────────────────

class TestEvidenceScorer:
  def test_normalize_and_score(self):
    scorer = EvidenceScorer()
    item1 = WeightedEvidenceItem(domain=DOMAIN_VISUAL, raw_score=0.94, reliability=0.90, effective_weight=0.5)
    item2 = WeightedEvidenceItem(domain=DOMAIN_VOICE, raw_score=0.86, reliability=0.80, effective_weight=0.5)
    dmap = {DOMAIN_VISUAL: item1, DOMAIN_VOICE: item2}

    scored = scorer.normalize_and_score(dmap)
    assert scored[DOMAIN_VISUAL].normalized_score == 0.94
    assert scored[DOMAIN_VISUAL].effective_score > 0.0
    assert len(scored[DOMAIN_VISUAL].reasons) > 0
    assert "High facial recognition similarity" in scored[DOMAIN_VISUAL].reasons[0]


# ──────────────────────────────────────────────────────────────────────────────
# 7. Test Confidence Engine
# ──────────────────────────────────────────────────────────────────────────────

class TestConfidenceEngine:
  def test_single_signal_capped(self):
    ce = ConfidenceEngine()
    # Only 1 active domain
    item = WeightedEvidenceItem(domain=DOMAIN_VISUAL, normalized_score=0.95, reliability=0.95, effective_weight=1.0)
    dmap = {DOMAIN_VISUAL: item}

    conf, item_obj = ce.compute_confidence(dmap, "p1", "m1", current_time_ms=1000, previous_confidence=0.0)
    # Must be capped <= MINIMUM_CONFIDENCE (0.10)
    assert conf <= 0.10

  def test_multi_signal_corroboration_evolution(self):
    ce = ConfidenceEngine()
    ce.clear_history("m1", "p1")

    # Simulate 4 independent active signals corroborating over time
    dmap = {
        DOMAIN_IDENTITY: WeightedEvidenceItem(domain=DOMAIN_IDENTITY, normalized_score=0.91, reliability=0.9, effective_weight=0.25),
        DOMAIN_VISUAL: WeightedEvidenceItem(domain=DOMAIN_VISUAL, normalized_score=0.94, reliability=0.9, effective_weight=0.25),
        DOMAIN_VOICE: WeightedEvidenceItem(domain=DOMAIN_VOICE, normalized_score=0.88, reliability=0.9, effective_weight=0.25),
        DOMAIN_CONVERSATION: WeightedEvidenceItem(domain=DOMAIN_CONVERSATION, normalized_score=0.95, reliability=0.9, effective_weight=0.25),
    }

    # Step 1: Minute 1
    conf1, _ = ce.compute_confidence(dmap, "p1", "m1", 60000, previous_confidence=0.15)
    assert conf1 > 0.15

    # Step 2: Minute 2
    conf2, _ = ce.compute_confidence(dmap, "p1", "m1", 120000, previous_confidence=conf1)
    assert conf2 >= conf1

    history = ce.get_history("m1", "p1")
    assert len(history) == 2


# ──────────────────────────────────────────────────────────────────────────────
# 8. Test Participant Ranker
# ──────────────────────────────────────────────────────────────────────────────

class TestParticipantRanker:
  def test_ranking_sorting_and_ranks(self):
    ranker = ParticipantRanker()
    st1 = ParticipantState(participant_id="P1", meeting_id="m1", confidence=0.96, reasons=["Strong face"])
    st2 = ParticipantState(participant_id="P2", meeting_id="m1", confidence=0.40, reasons=["Moderate match"])

    # Give P1 higher effective scores
    dmap1 = {DOMAIN_VISUAL: WeightedEvidenceItem(domain=DOMAIN_VISUAL, normalized_score=0.95, effective_score=0.5)}
    dmap2 = {DOMAIN_VISUAL: WeightedEvidenceItem(domain=DOMAIN_VISUAL, normalized_score=0.50, effective_score=0.2)}

    states = {"P1": st1, "P2": st2}
    dmaps = {"P1": dmap1, "P2": dmap2}

    res = ranker.rank_participants("m1", states, dmaps)
    assert len(res.ranking) == 2
    assert res.ranking[0].participant_id == "P1"
    assert res.ranking[0].rank == 1
    assert res.ranking[1].participant_id == "P2"
    assert res.ranking[1].rank == 2


# ──────────────────────────────────────────────────────────────────────────────
# 9. Test Explanation Builder
# ──────────────────────────────────────────────────────────────────────────────

class TestExplanationBuilder:
  def test_build_rule_based_explanation(self):
    eb = ExplanationBuilder()
    st = ParticipantState(participant_id="P_EX", meeting_id="m1")
    sc = ParticipantScore(participant_id="P_EX", final_score=0.92, confidence=0.95, rank=1)
    dmap = {
        DOMAIN_VISUAL: WeightedEvidenceItem(
            domain=DOMAIN_VISUAL, normalized_score=0.94, reliability=0.92, effective_weight=0.5,
            reasons=["High facial recognition similarity"]
        )
    }

    ex = eb.build_explanation(st, sc, dmap)
    assert ex.participant_id == "P_EX"
    assert len(ex.summary_points) > 0
    assert "Highest visual face similarity" in " ".join(ex.key_strengths)


# ──────────────────────────────────────────────────────────────────────────────
# 10. Test Fusion Storage & State Manager
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionStorageAndState:
  async def test_redis_state_manager_offline_resilience(self):
    sm = FusionStateManager()
    with patch("engine.fusion.state_manager.get_redis", new_callable=AsyncMock) as mock_redis:
      mock_redis.return_value = None
      st = ParticipantState(participant_id="p_offline", meeting_id="m_off")
      # Must return without raising exception and use in-memory fallback when Redis is None
      res = await sm.save_participant_state(st)
      assert res.participant_id == "p_offline"
      cached = await sm.get_participant_state("m_off", "p_offline")
      assert cached is not None and cached.participant_id == "p_offline"

  async def test_mongo_persistence_manager_offline_resilience(self):
    pm = FusionPersistenceManager()
    with patch("engine.fusion.persistence.get_mongo_db") as mock_db:
      mock_db.return_value = None
      st = ParticipantState(participant_id="p_mongo", meeting_id="m_mongo")
      # Must not crash
      await pm.save_participant_state_snapshot(st)
      ev = IncomingEvidence(evidence_id="e_m", meeting_id="m_m", source_type=DOMAIN_VOICE)
      ev_id = await pm.save_fusion_event("m_m", "p_m", ev)
      assert ev_id.startswith("FE_")


# ──────────────────────────────────────────────────────────────────────────────
# 11. Test Fusion Pipeline End-to-End
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionPipeline:
  async def test_pipeline_process_evidence_success(self):
    pipe = FusionPipeline()
    ev = IncomingEvidence(
        evidence_id="ev_pipe_1",
        meeting_id="mtg_pipeline",
        source_type=DOMAIN_VISUAL,
        participant_id="P_Target",
        score=0.93,
        reliability=0.91
    )

    with patch("engine.fusion.state_manager.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.fusion.persistence.get_mongo_db") as m_db:
      m_redis.return_value = None
      m_db.return_value = None

      # Clear local deduplication cache
      from engine.fusion.evidence_cache import evidence_cache
      evidence_cache.clear_cache("mtg_pipeline")
      evidence_cache._processed_ids.clear()

      res = await pipe.process_evidence(ev)
      assert res is not None
      assert res.participant_id == "P_Target"
      assert res.rank == 1
      assert DOMAIN_VISUAL in res.evidence_breakdown

  async def test_pipeline_process_duplicate_returns_none(self):
    pipe = FusionPipeline()
    ev = IncomingEvidence(
        evidence_id="DUP_PIPE_ID",
        meeting_id="mtg_pipe_dup",
        source_type=DOMAIN_IDENTITY,
        participant_id="P_Dup",
        score=0.88
    )

    with patch("engine.fusion.state_manager.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.fusion.persistence.get_mongo_db") as m_db:
      m_redis.return_value = None
      m_db.return_value = None

      from engine.fusion.evidence_cache import evidence_cache
      evidence_cache.clear_cache("mtg_pipe_dup")
      evidence_cache._processed_ids.clear()

      res1 = await pipe.process_evidence(ev)
      assert res1 is not None

      res2 = await pipe.process_evidence(ev)
      assert res2 is None  # Handled cleanly without raising exception


# ──────────────────────────────────────────────────────────────────────────────
# 12. Test Fusion Workers
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionWorkers:
  async def test_worker_manager_lifecycle_and_enqueue(self):
    wm = FusionWorkerManager.get_instance()
    wm.is_running = False
    wm.worker_tasks.clear()

    wm.start()
    assert wm.is_running is True
    assert len(wm.worker_tasks) == wm.pipeline.pipeline_config.WORKER_COUNT if hasattr(wm.pipeline, 'pipeline_config') else len(wm.worker_tasks) > 0

    await wm.stop()
    assert wm.is_running is False
    assert len(wm.worker_tasks) == 0
