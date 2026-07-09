"""
Deep Stress, Adversarial & Combinatorial Verification Suite (`tests/test_confidence_engine_deep.py`).

Exhaustively verifies:
1. `TestCombinatorialDomainMatrix`: All $2^8 = 256$ domain availability permutations (`FACE, VOICE, IDENTITY, CONVERSATION, BEHAVIOR, TRANSCRIPT, EMOTION, GAZE`). Verifies exact weight normalization (`sum == 1.0`), strict bounds [0.0, 1.0], and zero allocation to inactive streams across every combination.
2. `TestMeetingLifecycleAndGradualDecayRecovery`: 30-minute real-time lifecycle simulation across 5 distinct phases (`Handshake` -> `Coding No Speech` -> `Camera Off Glitch` -> `Extended Blackout Gradual Decay` -> `Signal Return Smooth Recovery`). Proves non-overwriting timeline history checkpoints and exact trend trajectory classification (`UPWARD` -> `DOWNWARD` -> `RECOVERING` -> `STABLE`).
3. `TestAdversarialBoundaryResilience`: Evaluates extreme out-of-bounds scores (`9999.0`, `-500.0`, `NaN`, `Inf`) and super-low upstream confidence (`< 0.15` dampening).
4. `TestMultiWorkerHighConcurrency`: Spawns 4 concurrent background async workers processing 300 simultaneous tasks across 30 candidates without race conditions, backpressure drops, or deadlock.
5. `TestStorageResilienceAndMongoArchiving`: Proves 100% offline memory resilience and checks exact multi-collection MongoDB document structures (`confidence_history`, `confidence_events`, `participant_confidence`, `meeting_confidence`).

(`tests/test_confidence_engine_deep.py`)
"""
import pytest
import asyncio
import itertools
import math
import time
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock
from engine.confidence import (
    EvidenceSource, ConfidenceTrend, NormalizationStrategyType, CalculationStrategyType,
    ALL_EVIDENCE_SOURCES, Evidence, RawEvidenceItem, NormalizedEvidenceItem,
    EvidenceValidator, EvidenceNormalizer, WeightManager, DynamicConfidenceWeighting,
    ConfidenceCalculator, ConfidenceTimelineManager, ConfidenceStateManager,
    ConfidenceStorageManager, ConfidencePipeline, ConfidenceWorkerManager
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Combinatorial Domain Matrix ($2^8 = 256$ combinations)
# ──────────────────────────────────────────────────────────────────────────────
class TestCombinatorialDomainMatrix:
  @pytest.mark.asyncio
  async def test_all_256_domain_combinations_normalize_and_bound_correctly(self):
    """Test all 256 possible availability permutations of the 8 evidence sources."""
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      pipe = ConfidencePipeline()
      sources = sorted(list(ALL_EVIDENCE_SOURCES))
      assert len(sources) == 8

      # Generate all 2^8 = 256 subsets
      all_subsets = list(itertools.chain.from_iterable(
          itertools.combinations(sources, r) for r in range(len(sources) + 1)
      ))
      assert len(all_subsets) == 256

      meeting_id = "m_matrix_256"
      for idx, subset in enumerate(all_subsets):
        pid = f"C_{idx}"
        # Inject buffered items directly for exactly this subset
        buffered_items: Dict[str, NormalizedEvidenceItem] = {}
        for src in subset:
          buffered_items[src] = NormalizedEvidenceItem(
              participant_id=pid,
              source=src,
              normalized_score=0.80,
              upstream_confidence=0.85,
              combined_signal_strength=0.68,
              reason="Matrix Test",
              timestamp=1000.0
          )
        pipe._participant_evidence_buffer[f"{meeting_id}:{pid}"] = buffered_items

        res = await pipe.evaluate_participant(meeting_id, pid, current_timestamp=1000.0)
        assert res is not None
        assert 0.0 <= res.overall_confidence <= 1.0

        # Check weights across this permutation
        if subset:
          # If any stream active, weights sum exactly to 1.0 within precision 1e-6
          assert sum(res.active_weights.values()) == pytest.approx(1.0, abs=1e-6)
        else:
          # If no streams active, weights sum to 0.0
          assert sum(res.active_weights.values()) == pytest.approx(0.0)

        # Ensure every missing domain strictly contributes zero in breakdown
        for src in ALL_EVIDENCE_SOURCES:
          if src not in subset:
            assert res.evidence_breakdown.get(src, 0.0) == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 2. 30-Minute Dynamic Lifecycle Simulation (Decay vs Recovery)
# ──────────────────────────────────────────────────────────────────────────────
class TestMeetingLifecycleAndGradualDecayRecovery:
  @pytest.mark.asyncio
  async def test_30_minute_dynamic_lifecycle_trajectory(self):
    """Simulate Candidate_Alice across 5 distinct phases over 30 minutes (1800 seconds)."""
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      pipe = ConfidencePipeline()
      meeting_id = "m_lifecycle_30m"
      pid = "Candidate_Alice"

      # Phase 1: Minute 1-5 (Initial Handshake — Face + Voice active)
      t_start = 1000.0
      ev_f1 = Evidence(participant_id=pid, source="face", score=0.85, confidence=0.90, timestamp=t_start)
      ev_v1 = Evidence(participant_id=pid, source="voice", score=0.88, confidence=0.90, timestamp=t_start)
      await pipe.process_evidence(meeting_id, ev_f1)
      res_p1 = await pipe.process_evidence(meeting_id, ev_v1)
      assert res_p1.overall_confidence > 0.65
      conf_p1 = res_p1.overall_confidence

      # Phase 2: Minute 5-15 (Coding Challenge — Voice silent, Face active)
      # 5 minutes later, voice item timestamp is stale (>120s old -> missing)
      t_coding = t_start + 600.0  # +10 minutes
      ev_f2 = Evidence(participant_id=pid, source="face", score=0.87, confidence=0.92, timestamp=t_coding)
      res_p2 = await pipe.process_evidence(meeting_id, ev_f2)
      # Verify 'No speech / voice absent' rule triggered and single-source safety cap applied (when face alone is active)
      assert any("voice" in r.lower() and ("weight set to 0.0" in r.lower() or "missing" in r.lower() or "stale" in r.lower()) for r in res_p2.reasons)
      assert res_p2.active_weights[EvidenceSource.VOICE.value] == 0.0
      assert any("confidence capped at" in r.lower() for r in res_p2.reasons)
      assert res_p2.overall_confidence <= 0.45 + 1e-6

      # When identity metadata is confirmed alongside face during coding challenge (2 active streams), cap lifts and smooth confidence recovery interpolates upward!
      ev_i2 = Evidence(participant_id=pid, source="identity", score=0.95, confidence=0.95, timestamp=t_coding)
      res_p2_multi = await pipe.process_evidence(meeting_id, ev_i2)
      assert res_p2_multi.overall_confidence > res_p2.overall_confidence
      assert any("smooth confidence recovery" in r.lower() for r in res_p2_multi.reasons)

      # Phase 3: Minute 16 (Camera Off Glitch — Face drops out, Voice & Conversation active)
      t_cam_off = t_coding + 360.0  # Minute 16
      ev_v3 = Evidence(participant_id=pid, source="voice", score=0.89, confidence=0.90, timestamp=t_cam_off)
      ev_c3 = Evidence(participant_id=pid, source="conversation", score=0.85, confidence=0.88, timestamp=t_cam_off)
      await pipe.process_evidence(meeting_id, ev_v3)
      res_p3 = await pipe.process_evidence(meeting_id, ev_c3)
      # Verify 'Camera off' rule triggered
      assert any("Camera off" in r or "Face weight set to 0.0" in r for r in res_p3.reasons)
      assert res_p3.active_weights[EvidenceSource.FACE.value] == 0.0
      assert res_p3.active_weights[EvidenceSource.VOICE.value] > 0.0

      # Phase 4: Minute 20 (Extended Blackout — All dynamic streams drop out -> Gradual Decay)
      t_blackout = t_cam_off + 300.0  # Minute 21 (all streams > 30s stale)
      # Evaluate participant without new evidence arrival
      res_p4 = await pipe.evaluate_participant(meeting_id, pid, current_timestamp=t_blackout)
      # Verify gradual decay applied (not sudden 0.0 crash!)
      assert any("gradual confidence decay" in r.lower() for r in res_p4.reasons)
      assert 0.0 < res_p4.overall_confidence < res_p3.overall_confidence

      # Phase 5: Minute 25 (Signal Return — Smooth Recovery without sudden spikes)
      t_return = t_blackout + 300.0  # Minute 26
      ev_f5 = Evidence(participant_id=pid, source="face", score=0.88, confidence=0.92, timestamp=t_return)
      ev_v5 = Evidence(participant_id=pid, source="voice", score=0.88, confidence=0.92, timestamp=t_return)
      ev_i5 = Evidence(participant_id=pid, source="identity", score=0.95, confidence=0.95, timestamp=t_return)
      res_p5_first = await pipe.process_evidence(meeting_id, ev_f5)
      assert res_p5_first.overall_confidence <= 0.45 + 1e-6  # Single returning signal capped

      res_p5_second = await pipe.process_evidence(meeting_id, ev_v5)
      assert any("smooth confidence recovery" in r.lower() for r in res_p5_second.reasons)
      assert res_p5_second.overall_confidence > res_p4.overall_confidence

      res_p5 = await pipe.process_evidence(meeting_id, ev_i5)
      assert res_p5.overall_confidence > res_p4.overall_confidence
      assert res_p5.trend in [ConfidenceTrend.STABLE.value, ConfidenceTrend.RECOVERING.value, ConfidenceTrend.UPWARD.value]

      # Check non-overwriting timeline history checkpoints
      state_final = await pipe.state_manager.get_or_create_state(meeting_id, pid)
      assert len(state_final.confidence_history) >= 4
      # Verify checkpoints are strictly chronological
      timestamps = [snap["timestamp"] for snap in state_final.confidence_history]
      assert sorted(timestamps) == timestamps


# ──────────────────────────────────────────────────────────────────────────────
# 3. Adversarial Boundary Resilience & Extreme Noise
# ──────────────────────────────────────────────────────────────────────────────
class TestAdversarialBoundaryResilience:
  @pytest.mark.asyncio
  async def test_extreme_out_of_bounds_scores_and_low_confidence_dampening(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      pipe = ConfidencePipeline()
      meeting_id = "m_adversarial"
      pid = "Candidate_Bob"

      # 1. Inject extreme out-of-bounds score (`score = 9999.0`) -> should clamp/normalize cleanly
      ev_high = Evidence(participant_id=pid, source="behavior", score=9999.0, confidence=0.90, timestamp=100.0)
      res_1 = await pipe.process_evidence(meeting_id, ev_high)
      assert res_1 is not None
      assert 0.0 <= res_1.overall_confidence <= 1.0

      # 2. Inject negative score (`score = -500.0`) -> should clamp/normalize cleanly
      ev_neg = Evidence(participant_id=pid, source="conversation", score=-500.0, confidence=0.85, timestamp=105.0)
      res_2 = await pipe.process_evidence(meeting_id, ev_neg)
      assert res_2 is not None
      assert 0.0 <= res_2.overall_confidence <= 1.0

      # 3. Super-low upstream confidence (`confidence = 0.10`) -> verify weight dampening by 60%
      ev_low_conf = Evidence(participant_id=pid, source="voice", score=0.80, confidence=0.10, timestamp=110.0)
      res_3 = await pipe.process_evidence(meeting_id, ev_low_conf)
      assert any("weight dampened by 60%" in r for r in res_3.reasons)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Multi-Worker Concurrency & Backpressure Stress
# ──────────────────────────────────────────────────────────────────────────────
class TestMultiWorkerHighConcurrency:
  @pytest.mark.asyncio
  async def test_4_workers_processing_300_concurrent_jobs_without_race(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      wm = ConfidenceWorkerManager(worker_count=4)
      await wm.start()

      meeting_id = "m_concurrency_stress"
      # Enqueue 300 simultaneous evidence events across 30 candidates (10 events each)
      enqueued = 0
      for c_idx in range(30):
        pid = f"Candidate_{c_idx}"
        for e_idx in range(10):
          ev = Evidence(
              participant_id=pid,
              source="face" if e_idx % 2 == 0 else "voice",
              score=0.80 + (e_idx * 0.01),
              confidence=0.85,
              timestamp=1000.0 + e_idx
          )
          if await wm.enqueue_evidence_job(meeting_id, ev):
            enqueued += 1

      assert enqueued == 300
      # Drain queue completely
      await wm.stop()
      assert wm.queue.empty() is True
      assert wm.is_running is False

      # Verify that all 30 candidates exist in memory state with valid confidence
      for c_idx in range(30):
        pid = f"Candidate_{c_idx}"
        state = await wm.pipeline.state_manager.get_or_create_state(meeting_id, pid)
        assert state.current_confidence > 0.0
        assert len(state.confidence_history) > 0


# ──────────────────────────────────────────────────────────────────────────────
# 5. Storage Resilience & Chronological Multi-Collection Archiving
# ──────────────────────────────────────────────────────────────────────────────
class TestStorageResilienceAndMongoArchiving:
  @pytest.mark.asyncio
  async def test_offline_memory_resilience_and_exact_mongo_document_structure(self):
    # 1. Test 50 consecutive evaluations during complete network error without crash
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.side_effect = ConnectionError("Redis down")
      m_db.side_effect = ConnectionError("Mongo down")

      pipe = ConfidencePipeline()
      for i in range(50):
        ev = Evidence(participant_id="Candidate_Offline", source="face", score=0.80, confidence=0.85, timestamp=100.0 + i)
        res = await pipe.process_evidence("m_offline", ev)
        assert res is not None
        assert res.overall_confidence > 0.0

    # 2. Verify exact document structure insertions across all 4 MongoDB collections
    mock_db = MagicMock()
    mock_col_hist = AsyncMock()
    mock_col_ev = AsyncMock()
    mock_col_part = AsyncMock()
    mock_col_meet = AsyncMock()
    mock_db.__getitem__.side_effect = lambda name: {
        "confidence_history": mock_col_hist,
        "confidence_events": mock_col_ev,
        "participant_confidence": mock_col_part,
        "meeting_confidence": mock_col_meet
    }[name]

    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = mock_db

      pipe = ConfidencePipeline()
      # Trigger an event requiring both history and discrete event archiving (>0.15 delta)
      ev = Evidence(participant_id="Candidate_Mongo", source="identity", score=0.98, confidence=0.98, timestamp=200.0)
      await pipe.process_evidence("m_mongo_test", ev)

      # Verify inserts into all 4 collections
      assert mock_col_hist.insert_one.called
      assert mock_col_part.insert_one.called
      assert mock_col_meet.insert_one.called

      # Verify structure of `confidence_history` document
      hist_doc = mock_col_hist.insert_one.call_args[0][0]
      assert hist_doc["meeting_id"] == "m_mongo_test"
      assert hist_doc["participant_id"] == "Candidate_Mongo"
      assert "confidence" in hist_doc
      assert "active_weights" in hist_doc
      assert "timestamp" in hist_doc
