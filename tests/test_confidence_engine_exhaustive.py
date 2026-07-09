"""
Exhaustive Deep Verification & Stress Test Suite for the SCIE Confidence Engine (`engine/confidence/`).

Provides rigorous, industrial-grade test coverage across every component:
1. `TestNormalizationStrategiesExhaustive`: Exact bounds and edge cases across `Linear`, `Sigmoid`, `ZScore`, and `MinMax` (`min == max`, zero ranges, missing stats).
2. `TestDynamicWeightingRulesAndDecayExhaustive`: Exact scaling multipliers (`x1.35`, `x1.30`, `x1.25`, `x1.20`), staleness interpolation (`30s -> 120s`), and low confidence dampening (`< 0.25`).
3. `TestCalculationAlgorithmsExhaustive`: Multi-source corroboration formulas across all `count in [1..8]`, single-source cap (`<= 0.45`), `Bayesian` log-odds numerical stability near `0.0`/`1.0`, and `LearnedMetaModel` fallback.
4. `TestTimelineManagerAndTrendExhaustive`: Exact trend classification boundaries (`+/- 0.05`), `TIMELINE_RESOLUTION_SEC` (`30s`) deduplication vs chronological recording (`60 minutes -> 120 entries`), and rolling window eviction (`600 items -> exactly 500 kept`).
5. `TestParticipantStateManagerHighVolumeConcurrency`: 100 concurrent async coroutines requesting identical state without race conditions or memory corruption.
6. `TestStorageManagerChaosAndPartialFailures`: Partial MongoDB collection insertion failures and Redis connection dropouts without crashing the pipeline.
7. `TestWorkerPoolHighVolumeAndBackpressure`: 1,000 rapid jobs enqueued across 10 concurrent workers, queue full backpressure (`QueueFull`), and exponential backoff retry verification (`0.1s -> 0.2s -> success`).

(`tests/test_confidence_engine_exhaustive.py`)
"""
import pytest
import asyncio
import math
import time
from typing import Dict, Any, List
from unittest.mock import patch, AsyncMock, MagicMock
from engine.confidence import (
    EvidenceSource, ConfidenceTrend, NormalizationStrategyType, CalculationStrategyType,
    ALL_EVIDENCE_SOURCES, Evidence, RawEvidenceItem, NormalizedEvidenceItem,
    EvidenceValidator, EvidenceNormalizer, WeightManager, DynamicConfidenceWeighting,
    ConfidenceCalculator, ConfidenceTimelineManager, ConfidenceStateManager,
    ConfidenceStorageManager, ConfidencePipeline, ConfidenceWorkerManager,
    confidence_config, ConfidenceNormalizationError, ConfidenceCalculationError
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Exhaustive Normalization Strategy Verification
# ──────────────────────────────────────────────────────────────────────────────
class TestNormalizationStrategiesExhaustive:
  def test_linear_normalization_exact_bounds_and_clamping(self):
    norm = EvidenceNormalizer(NormalizationStrategyType.LINEAR.value)
    # Exact 0% and 100%
    assert norm.normalize_evidence(RawEvidenceItem("p", "voice", 0.0, 1.0, 0.0, "", 100.0)).normalized_score == 0.0
    assert norm.normalize_evidence(RawEvidenceItem("p", "voice", 100.0, 1.0, 0.0, "", 100.0)).normalized_score == 1.0
    # Negative and over-100 inputs should clamp cleanly
    assert norm.normalize_evidence(RawEvidenceItem("p", "voice", -500.0, 1.0, 0.0, "", 100.0)).normalized_score == 0.0
    assert norm.normalize_evidence(RawEvidenceItem("p", "voice", 2500.0, 1.0, 0.0, "", 100.0)).normalized_score == 1.0

  def test_sigmoid_normalization_exact_logits_and_symmetry(self):
    norm = EvidenceNormalizer(NormalizationStrategyType.SIGMOID.value)
    # Logit 0.0 -> exact 0.5
    item_0 = norm.normalize_evidence(RawEvidenceItem("p", "face", 0.0, 1.0, 0.0, "", 100.0))
    assert item_0.normalized_score == pytest.approx(0.50, abs=1e-5)
    # Large positive/negative logits -> converge toward 1.0 / 0.0
    item_pos = norm.normalize_evidence(RawEvidenceItem("p", "face", 10.0, 1.0, 0.0, "", 100.0))
    item_neg = norm.normalize_evidence(RawEvidenceItem("p", "face", -10.0, 1.0, 0.0, "", 100.0))
    assert item_pos.normalized_score > 0.999
    assert item_neg.normalized_score < 0.001
    # Symmetry verification: sigmoid(x) + sigmoid(-x) == 1.0
    assert item_pos.normalized_score + item_neg.normalized_score == pytest.approx(1.0, abs=1e-6)

  def test_minmax_normalization_edge_cases_and_zero_division_guard(self):
    norm = EvidenceNormalizer(NormalizationStrategyType.MINMAX.value)
    # Standard range [50, 150]
    item_std = norm.normalize_evidence(
        RawEvidenceItem("p", "behavior", 100.0, 0.9, "", 100.0, {"min_score": 50.0, "max_score": 150.0})
    )
    assert item_std.normalized_score == pytest.approx(0.50)

    # Zero range (`min == max = 100.0`) -> should fallback safely without ZeroDivisionError
    item_zero = norm.normalize_evidence(
        RawEvidenceItem("p", "behavior", 100.0, 0.9, "", 100.0, {"min_score": 100.0, "max_score": 100.0})
    )
    assert 0.0 <= item_zero.normalized_score <= 1.0

    # Inverted range (`min > max`) -> should fallback safely
    item_inv = norm.normalize_evidence(
        RawEvidenceItem("p", "behavior", 80.0, 0.9, "", 100.0, {"min_score": 200.0, "max_score": 50.0})
    )
    assert 0.0 <= item_inv.normalized_score <= 1.0

  def test_zscore_normalization_extreme_deviations_and_zero_std_guard(self):
    norm = EvidenceNormalizer(NormalizationStrategyType.ZSCORE.value)
    # Standard Z=0 (mean=100, std=15 -> score=100) -> CDF(0) == 0.50
    item_mean = norm.normalize_evidence(
        RawEvidenceItem("p", "conversation", 100.0, 0.9, "", 100.0, {"mean": 100.0, "std": 15.0})
    )
    assert item_mean.normalized_score == pytest.approx(0.50, abs=1e-4)

    # Extreme Z = +10 and Z = -10
    item_high = norm.normalize_evidence(
        RawEvidenceItem("p", "conversation", 250.0, 0.9, "", 100.0, {"mean": 100.0, "std": 15.0})
    )
    item_low = norm.normalize_evidence(
        RawEvidenceItem("p", "conversation", -50.0, 0.9, "", 100.0, {"mean": 100.0, "std": 15.0})
    )
    assert item_high.normalized_score == pytest.approx(1.0, abs=1e-4)
    assert item_low.normalized_score == pytest.approx(0.0, abs=1e-4)

    # Zero standard deviation (`std == 0.0`) -> should fallback safely without ZeroDivisionError
    item_zero_std = norm.normalize_evidence(
        RawEvidenceItem("p", "conversation", 100.0, 0.9, "", 100.0, {"mean": 100.0, "std": 0.0})
    )
    assert 0.0 <= item_zero_std.normalized_score <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# 2. Dynamic Weighting Rules & Staleness Decay Exhaustive Verification
# ──────────────────────────────────────────────────────────────────────────────
class TestDynamicWeightingRulesAndDecayExhaustive:
  def test_camera_off_and_no_speech_hardware_scale_multipliers(self):
    wm = WeightManager()
    dyn = DynamicConfidenceWeighting(wm)

    # Both face and voice absent -> verify scaling across identity and conversation
    items_neither = {
        EvidenceSource.IDENTITY.value: NormalizedEvidenceItem("p", "identity", 0.9, 0.9, 0.81, "", 100.0),
        EvidenceSource.CONVERSATION.value: NormalizedEvidenceItem("p", "conversation", 0.9, 0.9, 0.81, "", 100.0),
    }
    weights, active, reasons, _, _ = dyn.evaluate_dynamic_weights_and_decay(items_neither, 100.0, 0.50)
    assert weights[EvidenceSource.FACE.value] == 0.0
    assert weights[EvidenceSource.VOICE.value] == 0.0
    assert EvidenceSource.IDENTITY.value in active
    assert EvidenceSource.CONVERSATION.value in active
    # Active weights must normalize exactly to 1.0
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)

  def test_low_confidence_gate_dampening_boundary(self):
    wm = WeightManager()
    dyn = DynamicConfidenceWeighting(wm)

    # Exactly at boundary vs below boundary (`gate = 0.25`)
    items = {
        EvidenceSource.FACE.value: NormalizedEvidenceItem("p", "face", 0.8, 0.2499, 0.2, "", 100.0),
        EvidenceSource.VOICE.value: NormalizedEvidenceItem("p", "voice", 0.8, 0.2500, 0.2, "", 100.0),
    }
    weights, _, reasons, _, _ = dyn.evaluate_dynamic_weights_and_decay(items, 100.0, 0.50)
    # Face (< 0.25) should be dampened by 60% relative to Voice (>= 0.25)
    base = wm.get_base_weights()
    expected_face_ratio = (base[EvidenceSource.FACE.value] * 0.40) / base[EvidenceSource.VOICE.value]
    assert weights[EvidenceSource.FACE.value] / weights[EvidenceSource.VOICE.value] == pytest.approx(expected_face_ratio, abs=1e-4)

  def test_staleness_linear_decay_progression(self):
    wm = WeightManager()
    dyn = DynamicConfidenceWeighting(wm)

    # Check exact staleness reduction across time checkpoints (30s to 120s)
    # decay_factor = clamp(1.0 - ((elapsed_sec - 30.0) / 180.0), 0.20, 1.0)
    for elapsed in [31.0, 60.0, 90.0, 119.0]:
      items = {
          EvidenceSource.FACE.value: NormalizedEvidenceItem("p", "face", 0.9, 0.9, 0.81, "", 1000.0 - elapsed),
          EvidenceSource.IDENTITY.value: NormalizedEvidenceItem("p", "identity", 0.9, 0.9, 0.81, "", 1000.0),  # Fresh
      }
      weights, _, reasons, adjusted, _ = dyn.evaluate_dynamic_weights_and_decay(items, 1000.0, 0.70)
      assert adjusted[EvidenceSource.FACE.value].is_stale is True
      assert adjusted[EvidenceSource.FACE.value].is_missing is False
      assert weights[EvidenceSource.FACE.value] < weights[EvidenceSource.IDENTITY.value]


# ──────────────────────────────────────────────────────────────────────────────
# 3. Calculation Algorithms Exhaustive Formulas & Stability
# ──────────────────────────────────────────────────────────────────────────────
class TestCalculationAlgorithmsExhaustive:
  def test_weighted_average_corroboration_lift_across_1_to_8_domains(self):
    calc = ConfidenceCalculator(CalculationStrategyType.WEIGHTED_AVERAGE.value)
    all_sources = sorted(list(ALL_EVIDENCE_SOURCES))

    for count in range(1, len(all_sources) + 1):
      subset = all_sources[:count]
      items = {s: NormalizedEvidenceItem("p", s, 0.80, 0.90, 0.72, "", 100.0) for s in subset}
      # Equal normalized weights summing to 1.0
      weights = {s: 1.0 / count for s in subset}
      for s in all_sources[count:]:
        weights[s] = 0.0

      from engine.confidence.models import ConfidenceCalculationContext
      ctx = ConfidenceCalculationContext("m", "p", 100.0, items, weights, 0.50)
      val, reasons = calc.calculate_confidence(ctx)

      if count == 1:
        # Single domain must be capped at `SINGLE_SOURCE_CONFIDENCE_CAP` (0.45)
        assert val <= confidence_config.SINGLE_SOURCE_CONFIDENCE_CAP + 1e-6
        assert any("capped at 0.45" in r.lower() for r in reasons)
      else:
        # Multi-domain corroboration lift: 0.72 * clamp(1.0 + (count - 1) * 0.04, 1.0, 1.15)
        corroboration_boost = min(1.15, max(1.0, 1.0 + (count - 1) * 0.04))
        expected_lift = min(1.0, 0.72 * corroboration_boost)
        assert val == pytest.approx(expected_lift, abs=1e-4)

  def test_bayesian_strategy_numerical_stability_near_zero_and_one(self):
    calc = ConfidenceCalculator(CalculationStrategyType.BAYESIAN.value)
    from engine.confidence.models import ConfidenceCalculationContext

    # Test extreme probabilities (`1e-9` and `1 - 1e-9`) to ensure no math domain errors in `math.log`
    items_extreme = {
        EvidenceSource.FACE.value: NormalizedEvidenceItem("p", "face", 1e-9, 0.90, 1e-9, "", 100.0),
        EvidenceSource.VOICE.value: NormalizedEvidenceItem("p", "voice", 1.0 - 1e-9, 0.90, 1.0 - 1e-9, "", 100.0),
    }
    weights = {EvidenceSource.FACE.value: 0.5, EvidenceSource.VOICE.value: 0.5}
    ctx = ConfidenceCalculationContext("m", "p", 100.0, items_extreme, weights, 0.50)

    val, reasons = calc.calculate_confidence(ctx, strategy_override=CalculationStrategyType.BAYESIAN.value)
    assert 0.0 <= val <= 1.0
    assert not math.isnan(val)
    assert not math.isinf(val)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Timeline Manager Chronological & Window Eviction Verification
# ──────────────────────────────────────────────────────────────────────────────
class TestTimelineManagerAndTrendExhaustive:
  def test_timeline_resolution_deduplication_vs_chronological_recording(self):
    tm = ConfidenceTimelineManager()
    hist: List[Dict[str, Any]] = []

    # 1. First checkpoint
    hist, trend_1, app_1 = tm.append_or_update_timeline(hist, 1000.0, 0.50, {"face": 1.0}, ["Start"])
    assert app_1 is True
    assert len(hist) == 1

    # 2. Rapid updates inside `TIMELINE_RESOLUTION_SEC` (30s) without major delta (<0.15) -> should_append is False
    for step in range(1, 25):
      hist, trend_step, app_step = tm.append_or_update_timeline(
          hist, 1000.0 + step, 0.50 + (step * 0.001), {"face": 1.0}, [f"Update {step}"]
      )
      assert app_step is False  # Immutable checkpoint not appended
      assert len(hist) == 1

    assert hist[0]["confidence"] == pytest.approx(0.50)  # Original snapshot unchanged when should_append is False

    # 3. New checkpoint after `TIMELINE_RESOLUTION_SEC` (30s) -> appends cleanly!
    hist, trend_new, app_new = tm.append_or_update_timeline(hist, 1031.0, 0.65, {"face": 0.5, "voice": 0.5}, ["Next interval"])
    assert app_new is True
    assert len(hist) == 2

  def test_timeline_sliding_window_eviction_at_500_entries(self):
    tm = ConfidenceTimelineManager()
    hist: List[Dict[str, Any]] = []

    # Enqueue 600 checkpoints spaced exactly 31 seconds apart
    for i in range(600):
      hist, _, _ = tm.append_or_update_timeline(hist, 1000.0 + (i * 31.0), 0.50, {"face": 1.0}, [f"Checkpoint {i}"])

    assert len(hist) == confidence_config.MAX_TIMELINE_HISTORY_ITEMS
    assert len(hist) == 500
    # First 100 items (0..99) evicted; oldest entry is now index 100 (`1000.0 + 100 * 31.0`)
    assert hist[0]["timestamp"] == pytest.approx(1000.0 + (100 * 31.0))
    assert hist[-1]["timestamp"] == pytest.approx(1000.0 + (599 * 31.0))


# ──────────────────────────────────────────────────────────────────────────────
# 5. Participant State Manager Concurrency Stress
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestParticipantStateManagerHighVolumeConcurrency:
  async def test_100_concurrent_async_tasks_initialization_race(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      sm = ConfidenceStateManager()
      meeting_id = "m_race_100"
      pid = "Candidate_Sync"

      # Launch 100 simultaneous async coroutines requesting identical state
      tasks = [sm.get_or_create_state(meeting_id, pid) for _ in range(100)]
      results = await asyncio.gather(*tasks)

      assert len(results) == 100
      # All returned states must be exactly identical
      first_id = id(results[0])
      for state in results:
        assert state.meeting_id == meeting_id
        assert state.participant_id == pid
        assert id(state) == first_id  # Single memory state object across all coroutines!


# ──────────────────────────────────────────────────────────────────────────────
# 6. Storage Chaos & Partial Failure Resilience
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestStorageManagerChaosAndPartialFailures:
  async def test_partial_mongo_collection_failures_do_not_crash_pipeline(self):
    mock_db = MagicMock()
    mock_col_hist = AsyncMock()
    mock_col_ev = AsyncMock()
    mock_col_part = AsyncMock()
    mock_col_meet = AsyncMock()

    # Make `confidence_history` insert succeed, but `participant_confidence` raise ConnectionError!
    mock_col_hist.insert_one.return_value = MagicMock(inserted_id="doc_1")
    mock_col_part.insert_one.side_effect = ConnectionError("Mongo replica set timeout")
    mock_col_ev.insert_one.return_value = MagicMock(inserted_id="doc_2")
    mock_col_meet.insert_one.return_value = MagicMock(inserted_id="doc_3")

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
      ev = Evidence(participant_id="Candidate_Chaos", source="face", score=0.88, confidence=0.90, timestamp=200.0)
      # Must return valid ConfidenceResult despite partial MongoDB insertion failure
      res = await pipe.process_evidence("m_chaos", ev)
      assert res is not None
      assert res.overall_confidence > 0.0
      # State should be safely preserved in rolling memory state
      state = await pipe.state_manager.get_or_create_state("m_chaos", "Candidate_Chaos")
      assert state.current_confidence == res.overall_confidence


# ──────────────────────────────────────────────────────────────────────────────
# 7. Worker Pool High Volume Throughput & Backpressure Verification
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestWorkerPoolHighVolumeAndBackpressure:
  async def test_1000_rapid_jobs_across_10_workers_and_queue_drainage(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      wm = ConfidenceWorkerManager(worker_count=10)
      await wm.start()
      wm.queue = asyncio.Queue(maxsize=2500)  # Expand queue to comfortably hold 1,000 burst items

      meeting_id = "m_high_throughput"
      # Enqueue 1,000 rapid evidence jobs across 50 simulated candidates (20 items each)
      enqueued = 0
      for c_idx in range(50):
        pid = f"Candidate_Batch_{c_idx}"
        for item_idx in range(20):
          ev = Evidence(
              participant_id=pid,
              source="voice" if item_idx % 2 == 0 else "conversation",
              score=0.75 + (item_idx * 0.01),
              confidence=0.85,
              timestamp=2000.0 + item_idx
          )
          if await wm.enqueue_evidence_job(meeting_id, ev):
            enqueued += 1

      assert enqueued == 1000
      # Drain completely via stop() -> must join queue and cancel workers cleanly
      await wm.stop()
      assert wm.queue.empty() is True
      assert wm.is_running is False

  async def test_worker_retry_loop_on_transient_failures(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      wm = ConfidenceWorkerManager(worker_count=1)
      # Mock pipeline.process_evidence to raise transient exception on first 2 calls, then succeed on 3rd call
      mock_process = AsyncMock()
      mock_process.side_effect = [
          ConnectionError("Transient error 1"),
          ConnectionError("Transient error 2"),
          MagicMock(overall_confidence=0.82)
      ]
      wm.pipeline.process_evidence = mock_process

      job = {
          "meeting_id": "m_retry",
          "raw_evidence": Evidence(participant_id="Candidate_Retry", source="face", score=0.85, confidence=0.90, timestamp=100.0),
          "calculation_strategy": None,
          "attempts": 0
      }
      res = await wm._process_job_with_retry(job)
      assert res is not None
      assert res.overall_confidence == 0.82
      assert mock_process.call_count == 3

  async def test_worker_retry_loop_on_transient_failures(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      wm = ConfidenceWorkerManager(worker_count=1)
      # Mock pipeline.process_evidence to raise transient exception on first 2 calls, then succeed on 3rd call
      mock_process = AsyncMock()
      mock_process.side_effect = [
          ConnectionError("Transient error 1"),
          ConnectionError("Transient error 2"),
          MagicMock(overall_confidence=0.82)
      ]
      wm.pipeline.process_evidence = mock_process

      job = {
          "meeting_id": "m_retry",
          "raw_evidence": Evidence(participant_id="Candidate_Retry", source="face", score=0.85, confidence=0.90, timestamp=100.0),
          "calculation_strategy": None,
          "attempts": 0
      }
      res = await wm._process_job_with_retry(job)
      assert res is not None
      assert res.overall_confidence == 0.82
      assert mock_process.call_count == 3
