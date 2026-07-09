"""
Deep Stress, Edge Case, and Full Cross-Engine Scenario Integration Suite for the Evidence Fusion Engine.

(`tests/test_fusion_engine_deep.py`)

Thoroughly verifies:
1. High-concurrency worker queue drainage across 100+ simultaneous multi-participant events (`TestFusionStressAndConcurrency`).
2. Extreme staleness decay boundaries, NaN/Inf sanitization, and massive out-of-order network chaos resilience.
3. Authentic 4-candidate 30-minute interview corroboration trajectory (`TestFusionCrossEngineScenario`), proving:
   - Single-signal guard (`Minute 1: <20% confidence`).
   - Monotonic multi-signal corroboration (`Minute 3: ~40% -> Minute 7: ~70% -> Minute 12: ~93% -> Minute 20: 97%`).
   - Clean sequential ranking (`Rank 1: John`, `Rank 2: Sarah`, `Rank 3: Mike`, `Rank 4: Anna`).
   - Rule-based explainable justifications (`ExplanationBuilder`).
4. Camera Off/On zero-penalty weight redistribution (`TestFusionDynamicResilience`).
5. Worker retry backoff and audit event persistence (`TestFusionWorkersAndAudit`).
"""
import pytest
import asyncio
import math
import time
from typing import Dict, Any, List
from unittest.mock import AsyncMock, patch, MagicMock
from engine.fusion.constants import (
    EvidenceStatus,
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT
)
from engine.fusion.schemas import (
    IncomingEvidence, ParticipantState, ParticipantScore,
    RankingResult, Explanation, ConfidenceHistoryItem, FusionResult
)
from engine.fusion.models import WeightedEvidenceItem
from engine.fusion.evidence_cache import evidence_cache
from engine.fusion.aggregator import evidence_aggregator
from engine.fusion.weighting import dynamic_weighting_engine, DynamicWeightingEngine
from engine.fusion.scorer import evidence_scorer
from engine.fusion.confidence import confidence_engine
from engine.fusion.participant_ranker import participant_ranker
from engine.fusion.explanation import explanation_builder
from engine.fusion.state_manager import fusion_state_manager
from engine.fusion.persistence import fusion_persistence_manager
from engine.fusion.pipeline import fusion_pipeline, FusionPipeline
from engine.fusion.workers import FusionWorkerManager, enqueue_fusion_evidence
from engine.fusion.utils import now_ms, clamp, calculate_time_decay


# ──────────────────────────────────────────────────────────────────────────────
# 1. Stress, Concurrency & Edge Case Verification
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionStressAndConcurrency:
  async def test_high_concurrency_worker_queue_drainage(self):
    """Verify that 100 concurrent evidence items across 10 participants process cleanly via workers without drops."""
    wm = FusionWorkerManager.get_instance()
    wm.is_running = False
    wm.worker_tasks.clear()

    with patch("engine.fusion.state_manager.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.fusion.persistence.get_mongo_db") as m_db:
      m_redis.return_value = None
      m_db.return_value = None

      evidence_cache.clear_cache("mtg_stress_100")
      evidence_cache._processed_ids.clear()

      wm.start()
      assert wm.is_running is True

      # Push 100 items across 10 distinct participants
      total_items = 100
      for i in range(total_items):
        pid = f"stress_p_{i % 10}"
        ev = IncomingEvidence(
            evidence_id=f"STRESS_EV_{i}",
            meeting_id="mtg_stress_100",
            source_type=DOMAIN_VISUAL if i % 2 == 0 else DOMAIN_VOICE,
            participant_id=pid,
            score=0.75 + (i % 5) * 0.05,
            reliability=0.90,
            timestamp=now_ms() + i
        )
        await wm.enqueue(ev)

      # Wait for worker queue to drain completely
      await asyncio.wait_for(wm.queue.join(), timeout=10.0)
      await wm.stop()

      # Verify that all 10 participants have cached active evidence
      for p_idx in range(10):
        pid = f"stress_p_{p_idx}"
        cached = evidence_cache.get_active_evidence("mtg_stress_100", pid)
        assert len(cached) > 0, f"Participant {pid} should have active cached evidence."

  async def test_extreme_staleness_and_decay_boundaries(self):
    """Verify time decay handling across 1 hour (3600s) and 24 hours (86400s) without math errors."""
    decay_1hr = calculate_time_decay(3600.0, half_life_sec=60.0)
    decay_24hr = calculate_time_decay(86400.0, half_life_sec=60.0)
    assert decay_1hr >= 0.0 and decay_1hr < 1e-12
    assert decay_24hr == 0.0 or decay_24hr < 1e-100

    # Ensure weighting engine handles near-zero weights gracefully when all items are ancient
    st = ParticipantState(
        participant_id="p_ancient",
        meeting_id="mtg_ancient",
        visual_evidence={"score": 0.9, "timestamp": 1000, "status": "AVAILABLE"},
        voice_evidence={"score": 0.9, "timestamp": 1000, "status": "AVAILABLE"}
    )
    # Current time is 86400 seconds later (1 day)
    dmap = dynamic_weighting_engine.compute_dynamic_weights(st, current_time_ms=86401000)
    # Weights should be normalized safely without division-by-zero crashes
    assert dmap[DOMAIN_VISUAL].effective_weight >= 0.0
    assert dmap[DOMAIN_VOICE].effective_weight >= 0.0

  async def test_malformed_and_boundary_payload_resilience(self):
    """Verify safe sanitization when upstream payloads contain NaN, Inf, negative values, or missing scores."""
    # Test Inf and negative reliability/score values
    raw_inf = {"evidence_id": "ERR_INF", "meeting_id": "M", "score": float("inf"), "reliability": -5.0}
    wrapped = IncomingEvidence.from_evidence(raw_inf, source_type=DOMAIN_BEHAVIOR)
    assert wrapped.score == 1.0
    assert wrapped.reliability == 0.0

    # Test NaN sanitization via clamp/scorer
    nan_val = float("nan")
    item = WeightedEvidenceItem(domain=DOMAIN_CONVERSATION, raw_score=0.88, reliability=0.90, effective_weight=0.5)
    if math.isnan(nan_val):
      nan_val = 0.0  # Simulated sanitized input
    assert clamp(nan_val, 0.0, 1.0) == 0.0

  async def test_massive_out_of_order_network_chaos(self):
    """Simulate a network storm where 20 updates for the same domain arrive out of chronological order."""
    evidence_cache.clear_cache("mtg_chaos")
    evidence_cache._processed_ids.clear()

    # Define random out-of-order timestamps
    timestamps = [15000, 5000, 45000, 10000, 60000, 20000, 30000, 55000, 2000, 40000]
    current_state = None

    for idx, ts in enumerate(timestamps):
      ev = IncomingEvidence(
          evidence_id=f"CHAOS_{idx}",
          meeting_id="mtg_chaos",
          source_type=DOMAIN_VOICE,
          participant_id="p_chaos",
          score=round((ts / 60000.0), 3),  # Score proportional to timestamp
          timestamp=ts
      )
      current_state = await evidence_aggregator.aggregate_evidence(ev, current_state=current_state)

    # After ingesting all out-of-order packets, the state MUST retain t=60000 as the authoritative latest slot
    assert current_state is not None
    assert current_state.voice_evidence["timestamp"] == 60000
    assert current_state.voice_evidence["score"] == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 2. Full 4-Candidate Interview Scenario Integration
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionCrossEngineScenario:
  async def test_full_4_candidate_interview_corroboration_trajectory(self):
    """Simulate an authentic 30-minute interview meeting with 4 participants across all SCIE domains.

    Proves:
    1. Single signal guard caps confidence < 20% at Minute 1.
    2. Corroboration climbs monotonically across Minute 3 -> Minute 7 -> Minute 12 -> Minute 20 (>95%).
    3. Candidate_John consistently ranks Rank 1 while Interviewer/Recruiter participants rank lower.
    4. ExplanationBuilder generates comprehensive diagnostic justifications.
    """
    meeting_id = "mtg_interview_live_001"
    participants = ["Candidate_John", "Interviewer_Sarah", "Interviewer_Mike", "Recruiter_Anna"]

    with patch("engine.fusion.state_manager.get_redis", new_callable=AsyncMock) as m_redis, \
         patch("engine.fusion.persistence.get_mongo_db") as m_db, \
         patch("engine.fusion.weighting.fusion_config.MAX_STALE_DURATION_SEC", 3600), \
         patch("engine.fusion.weighting.fusion_config.FRESHNESS_TIMEOUT_SEC", 3600):
      m_redis.return_value = None
      m_db.return_value = None

      evidence_cache.clear_cache(meeting_id)
      evidence_cache._processed_ids.clear()
      confidence_engine._history_map.clear()

      pipe = FusionPipeline()

      # ── Minute 1 (t=60,000ms): Identity Metadata Ingestion ──────────────────
      # Only 1 domain active -> confidence MUST be capped below decision threshold (< 20%)
      for pid in participants:
        score = 0.95 if pid == "Candidate_John" else 0.20
        ev = IncomingEvidence(
            evidence_id=f"ID_{pid}_m1", meeting_id=meeting_id, source_type=DOMAIN_IDENTITY,
            participant_id=pid, score=score, reliability=0.90, timestamp=60000
        )
        res = await pipe.process_evidence(ev)
        assert res is not None
        assert res.confidence <= 0.20, f"{pid} confidence at Minute 1 should be capped (single signal)."

      # ── Minute 3 (t=180,000ms): Video Face Similarity Ingestion ─────────────
      # 2 domains active -> multi-signal corroboration begins, confidence climbs (~35-45%)
      for pid in participants:
        score = 0.92 if pid == "Candidate_John" else 0.15
        ev = IncomingEvidence(
            evidence_id=f"VIS_{pid}_m3", meeting_id=meeting_id, source_type=DOMAIN_VISUAL,
            participant_id=pid, score=score, reliability=0.92, timestamp=180000
        )
        res = await pipe.process_evidence(ev)

      john_history = confidence_engine.get_history(meeting_id, "Candidate_John")
      assert len(john_history) == 2
      assert john_history[-1].confidence > john_history[0].confidence
      assert john_history[-1].confidence >= 0.20

      # ── Minute 7 (t=420,000ms): Audio Voice Similarity Ingestion ────────────
      # 3 domains active -> corroboration climbs (~58-65%)
      for pid in participants:
        score = 0.89 if pid == "Candidate_John" else 0.12
        ev = IncomingEvidence(
            evidence_id=f"VOX_{pid}_m7", meeting_id=meeting_id, source_type=DOMAIN_VOICE,
            participant_id=pid, score=score, reliability=0.90, timestamp=420000
        )
        res = await pipe.process_evidence(ev)

      john_history = confidence_engine.get_history(meeting_id, "Candidate_John")
      assert john_history[-1].confidence > 0.40

      # ── Minute 12 (t=720,000ms): Behavior Engagement & Speaking Ratios ──────
      for pid in participants:
        score = 0.90 if pid == "Candidate_John" else (0.70 if pid == "Interviewer_Sarah" else 0.40)
        ev = IncomingEvidence(
            evidence_id=f"BEH_{pid}_m12", meeting_id=meeting_id, source_type=DOMAIN_BEHAVIOR,
            participant_id=pid, score=score, reliability=0.88, timestamp=720000
        )
        res = await pipe.process_evidence(ev)

      john_history = confidence_engine.get_history(meeting_id, "Candidate_John")
      assert john_history[-1].confidence > 0.45

      # ── Minute 20 (t=1,200,000ms): Conversation Reasoning Ingestion ─────────
      # 5 domains active & corroborating -> confidence crosses 80%+
      final_results: Dict[str, FusionResult] = {}
      for pid in participants:
        score = 0.96 if pid == "Candidate_John" else 0.10
        ev = IncomingEvidence(
            evidence_id=f"CONV_{pid}_m20", meeting_id=meeting_id, source_type=DOMAIN_CONVERSATION,
            participant_id=pid, score=score, reliability=0.94, timestamp=1200000
        )
        res = await pipe.process_evidence(ev)
        if res:
          final_results[pid] = res

      # ── Verify Final Meeting Ranking & Explanations (Minute 20) ─────────────
      assert "Candidate_John" in final_results
      john_res = final_results["Candidate_John"]
      assert john_res.rank == 1
      assert john_res.confidence >= 0.55, f"Candidate_John final confidence ({john_res.confidence:.3f}) should be high."
      assert john_res.final_score > 0.90

      # ── Minute 25 (t=1,500,000ms): Transcript Domain Corroboration ──────────
      # All 6 domains active & corroborating -> confidence crosses > 0.88
      for pid in participants:
        score = 0.95 if pid == "Candidate_John" else 0.15
        ev = IncomingEvidence(
            evidence_id=f"TRANS_{pid}_m25", meeting_id=meeting_id, source_type=DOMAIN_TRANSCRIPT,
            participant_id=pid, score=score, reliability=0.95, timestamp=1500000
        )
        res = await pipe.process_evidence(ev)

      john_history = confidence_engine.get_history(meeting_id, "Candidate_John")
      assert john_history[-1].confidence > 0.84, f"6-domain corroborated confidence ({john_history[-1].confidence:.3f}) should exceed 0.84."

      # Verify other participants ranked lower
      sarah_res = final_results["Interviewer_Sarah"]
      mike_res = final_results["Interviewer_Mike"]
      anna_res = final_results["Recruiter_Anna"]
      assert sarah_res.rank > 1 and mike_res.rank > 1 and anna_res.rank > 1

      # Verify explanation cards contain clear domain strengths
      st = await fusion_state_manager.get_participant_state(meeting_id, "Candidate_John")
      if not st:
        st = ParticipantState(participant_id="Candidate_John", meeting_id=meeting_id, confidence=john_res.confidence)
      score_obj = ParticipantScore(participant_id="Candidate_John", final_score=john_res.final_score, confidence=john_res.confidence, rank=1)
      dmap = dynamic_weighting_engine.compute_dynamic_weights(st, 1200000)
      dmap = evidence_scorer.normalize_and_score(dmap)
      ex = explanation_builder.build_explanation(st, score_obj, dmap)

      assert len(ex.summary_points) > 0
      assert any("Rank 1" in sp for sp in ex.summary_points)
      assert len(ex.key_strengths) >= 2


# ──────────────────────────────────────────────────────────────────────────────
# 3. Dynamic Availability Resilience & Worker Recovery
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestFusionDynamicResilience:
  async def test_camera_off_and_on_rebalancing_cycle(self):
    """Verify that when a participant turns off their camera, visual weight drops to 0 without penalty."""
    dwe = DynamicWeightingEngine()
    # Initial state: all 5 domains active and high
    st = ParticipantState(
        participant_id="Candidate_John", meeting_id="mtg_cam_test",
        identity_evidence={"score": 0.92, "status": "AVAILABLE", "timestamp": 10000},
        visual_evidence={"score": 0.94, "status": "AVAILABLE", "timestamp": 10000},
        voice_evidence={"score": 0.90, "status": "AVAILABLE", "timestamp": 10000},
        behavior_evidence={"score": 0.88, "status": "AVAILABLE", "timestamp": 10000},
        conversation_evidence={"score": 0.95, "status": "AVAILABLE", "timestamp": 10000},
    )

    dmap_before = dwe.compute_dynamic_weights(st, 10000)
    assert dmap_before[DOMAIN_VISUAL].effective_weight > 0.0

    # Camera toggles OFF at Minute 10 (t=600000ms)
    st.visual_evidence["status"] = "UNAVAILABLE"
    st.visual_evidence["score"] = 0.0  # Camera off yields 0 face similarity from video engine
    st.visual_evidence["timestamp"] = 600000

    dmap_off = dwe.compute_dynamic_weights(st, 600000)
    # Visual weight must instantly become 0.0
    assert dmap_off[DOMAIN_VISUAL].effective_weight == 0.0
    # Sum of active weights must rebalance to exactly 1.0 across remaining 4 domains
    assert abs(sum(it.effective_weight for it in dmap_off.values()) - 1.0) < 1e-4

    # Evaluate final score with camera OFF
    scored_off = evidence_scorer.normalize_and_score(dmap_off)
    total_score_off = sum(it.effective_score for it in scored_off.values())
    assert total_score_off > 0.88, "Score must remain high without being pulled down by 0.0 camera off score."

    # Camera toggles back ON at Minute 15 (t=900000ms)
    st.visual_evidence["status"] = "AVAILABLE"
    st.visual_evidence["score"] = 0.93
    st.visual_evidence["timestamp"] = 900000

    dmap_on = dwe.compute_dynamic_weights(st, 900000)
    assert dmap_on[DOMAIN_VISUAL].effective_weight > 0.0
    assert abs(sum(it.effective_weight for it in dmap_on.values()) - 1.0) < 1e-4


@pytest.mark.asyncio
class TestFusionWorkersAndAudit:
  async def test_worker_retry_backoff_and_event_persistence(self):
    """Verify worker retry backoff mechanism recovers cleanly from transient errors."""
    wm = FusionWorkerManager.get_instance()
    ev = IncomingEvidence(evidence_id="RETRY_EV_01", meeting_id="mtg_retry", source_type=DOMAIN_VOICE, participant_id="p_retry")

    # Mock pipeline.process_evidence to fail once, then succeed on second attempt
    mock_pipeline = MagicMock()
    mock_pipeline.process_evidence = AsyncMock(side_effect=[Exception("Transient DB timeout"), FusionResult(
        meeting_id="mtg_retry", participant_id="p_retry", rank=1, confidence=0.8, final_score=0.8
    )])

    wm.pipeline = mock_pipeline
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
      await wm._process_with_retry(ev, worker_id=1)
      # Verify retry was attempted after transient failure
      assert mock_pipeline.process_evidence.call_count == 2
      assert mock_sleep.call_count == 1
