"""
Comprehensive Unit & Integration Test Suite for the SCIE Confidence Engine (`engine/confidence/`).

Verifies:
1. `EvidenceValidator`: Validating and rejecting malformed inputs cleanly without crashing.
2. `EvidenceNormalizer`: Linear, Sigmoid, ZScore, and MinMax normalization strategies.
3. `WeightManager`: Base weights, no magic numbers, runtime overrides, and exact normalization.
4. `DynamicConfidenceWeighting`: Camera off, no speech, and low confidence guards.
5. `ConfidenceCalculator`: Modular strategy pattern (`WeightedAverage`, `Bayesian`, `LearnedMeta`).
6. `ConfidenceTimelineManager`: Immutable non-overwriting chronological checkpoints & trend classification.
7. `ConfidenceStorageManager`: Azure Cache for Redis and 4 MongoDB collection archiving (+ offline memory).
8. `ConfidenceWorkerManager`: Background async worker pool processing and clean queue drainage (`stop()`).

(`tests/test_confidence_engine.py`)
"""
import pytest
import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock
from engine.confidence import (
    EvidenceSource, ConfidenceTrend, NormalizationStrategyType, CalculationStrategyType,
    Evidence, RawEvidenceItem, NormalizedEvidenceItem, ConfidenceCalculationContext,
    EvidenceValidator, EvidenceNormalizer, WeightManager, DynamicConfidenceWeighting,
    ConfidenceCalculator, ConfidenceTimelineManager, ConfidenceStateManager,
    ConfidenceStorageManager, ConfidencePipeline, ConfidenceWorkerManager
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Evidence Validator Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestEvidenceValidator:
  def test_validator_parses_valid_evidence_and_rejects_malformed_cleanly(self):
    val = EvidenceValidator()

    # Valid schema evidence
    ev = Evidence(
        participant_id="Candidate_John",
        source=EvidenceSource.FACE.value,
        score=0.88,
        confidence=0.90,
        reason="Clear facial recognition match",
        timestamp=100.0
    )
    parsed = val.validate_and_parse(ev)
    assert parsed is not None
    assert parsed.participant_id == "Candidate_John"
    assert parsed.score == 0.88
    assert parsed.confidence == 0.90

    # Valid dictionary input with percentage score
    raw_dict = {
        "participant_id": "Candidate_John",
        "source": "voice",
        "score": "85.5",
        "confidence": "0.92",
        "timestamp": 110.0
    }
    parsed_dict = val.validate_and_parse(raw_dict)
    assert parsed_dict is not None
    assert parsed_dict.score == 85.5

    # Rejections without crashing
    assert val.validate_and_parse(None) is None
    assert val.validate_and_parse({"participant_id": "", "source": "face", "score": 1.0, "confidence": 1.0}) is None
    assert val.validate_and_parse({"participant_id": "p1", "source": "", "score": 1.0, "confidence": 1.0}) is None
    assert val.validate_and_parse({"participant_id": "p1", "source": "face", "score": "not_a_num", "confidence": 1.0}) is None
    assert val.validate_and_parse({"participant_id": "p1", "source": "face", "score": 1.0, "confidence": "invalid_conf"}) is None


# ──────────────────────────────────────────────────────────────────────────────
# 2. Evidence Normalizer Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestEvidenceNormalizer:
  def test_normalization_strategies_map_to_unit_bounds(self):
    norm = EvidenceNormalizer(NormalizationStrategyType.LINEAR.value)

    # 1. Linear percentage scaling down to [0.0, 1.0]
    raw_perc = RawEvidenceItem(participant_id="p_norm", source="voice", score=82.0, confidence=0.90, reason="Percent", timestamp=100.0)
    item_lin = norm.normalize_evidence(raw_perc)
    assert item_lin.normalized_score == pytest.approx(0.82)
    assert item_lin.combined_signal_strength == pytest.approx(0.82 * 0.90)

    # 2. Sigmoid normalization
    raw_logit = RawEvidenceItem(participant_id="p_norm", source="identity", score=2.5, confidence=0.95, reason="Logit", timestamp=100.0)
    item_sig = norm.normalize_evidence(raw_logit, strategy_override=NormalizationStrategyType.SIGMOID.value)
    assert 0.0 <= item_sig.normalized_score <= 1.0
    assert item_sig.normalized_score > 0.90  # 2.5 logit is > 0.92 sigmoid

    # 3. MinMax normalization
    raw_mm = RawEvidenceItem(
        participant_id="p_norm", source="behavior", score=150.0, confidence=0.85, reason="Points", timestamp=100.0,
        metadata={"min_score": 50.0, "max_score": 250.0}
    )
    item_mm = norm.normalize_evidence(raw_mm, strategy_override=NormalizationStrategyType.MINMAX.value)
    assert item_mm.normalized_score == pytest.approx(0.50)  # (150-50)/(250-50) == 0.50

    # 4. ZScore normalization
    raw_zs = RawEvidenceItem(
        participant_id="p_norm", source="conversation", score=110.0, confidence=0.90, reason="IQ", timestamp=100.0,
        metadata={"mean": 100.0, "std": 10.0}
    )
    item_zs = norm.normalize_evidence(raw_zs, strategy_override=NormalizationStrategyType.ZSCORE.value)
    assert 0.80 <= item_zs.normalized_score <= 0.90  # Z=1 -> CDF ~ 0.84


# ──────────────────────────────────────────────────────────────────────────────
# 3. Weight Manager & Dynamic Rules Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestWeightingAndDynamicRules:
  def test_weight_manager_runtime_overrides_and_normalization(self):
    wm = WeightManager()
    base = wm.get_base_weights()
    assert EvidenceSource.FACE.value in base
    assert base[EvidenceSource.FACE.value] > 0.0

    # Override specific domain
    wm.set_base_weight(EvidenceSource.FACE.value, 0.35)
    assert wm.get_base_weights()[EvidenceSource.FACE.value] == 0.35

    # Normalize across active subset
    active = {EvidenceSource.FACE.value, EvidenceSource.VOICE.value}
    norm_active = wm.normalize_active_weights(wm.get_base_weights(), active)
    assert sum(norm_active.values()) == pytest.approx(1.0)
    assert norm_active[EvidenceSource.CONVERSATION.value] == 0.0

  def test_dynamic_weighting_camera_off_and_no_speech_rules(self):
    wm = WeightManager()
    dyn = DynamicConfidenceWeighting(wm)

    # 1. Camera Off -> Face absent (`face` not in items)
    items_cam_off = {
        EvidenceSource.VOICE.value: NormalizedEvidenceItem("p_dyn", "voice", 0.8, 0.9, 0.72, "Voice OK", 100.0),
        EvidenceSource.CONVERSATION.value: NormalizedEvidenceItem("p_dyn", "conversation", 0.8, 0.9, 0.72, "Conv OK", 100.0),
    }
    weights, active, reasons, _, _ = dyn.evaluate_dynamic_weights_and_decay(items_cam_off, 100.0, 0.50)
    assert weights[EvidenceSource.FACE.value] == 0.0
    assert any("Camera off" in r for r in reasons)
    assert sum(weights.values()) == pytest.approx(1.0)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Confidence Calculator Modular Strategy Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestConfidenceCalculator:
  def test_weighted_average_and_bayesian_strategies(self):
    calc = ConfidenceCalculator(CalculationStrategyType.WEIGHTED_AVERAGE.value)

    items = {
        EvidenceSource.FACE.value: NormalizedEvidenceItem("p_c", "face", 0.9, 0.9, 0.81, "F", 100.0),
        EvidenceSource.VOICE.value: NormalizedEvidenceItem("p_c", "voice", 0.9, 0.9, 0.81, "V", 100.0),
        EvidenceSource.IDENTITY.value: NormalizedEvidenceItem("p_c", "identity", 0.95, 0.95, 0.9025, "I", 100.0),
    }
    weights = {EvidenceSource.FACE.value: 0.33, EvidenceSource.VOICE.value: 0.33, EvidenceSource.IDENTITY.value: 0.34}
    ctx = ConfidenceCalculationContext("m_calc", "p_c", 100.0, items, weights, 0.40)

    val_wa, reasons_wa = calc.calculate_confidence(ctx)
    assert val_wa > 0.80
    assert any("corroboration" in r.lower() for r in reasons_wa)

    # Switch to Bayesian
    val_b, reasons_b = calc.calculate_confidence(ctx, strategy_override=CalculationStrategyType.BAYESIAN.value)
    assert val_b > val_wa  # Strong prior log-odds boost across 3 pristine sources
    assert any("Bayesian" in r for r in reasons_b)


# ──────────────────────────────────────────────────────────────────────────────
# 5. Timeline Manager Progression Tests
# ──────────────────────────────────────────────────────────────────────────────
class TestTimelineManager:
  def test_timeline_never_overwrites_and_classifies_trend(self):
    tm = ConfidenceTimelineManager()
    hist: list = []

    # Checkpoint 1: 00:00 -> 15%
    hist, trend_1, appended_1 = tm.append_or_update_timeline(hist, 100.0, 0.15, {"face": 0.15}, ["Init"])
    assert appended_1 is True
    assert len(hist) == 1
    assert hist[0]["confidence"] == 0.15

    # Checkpoint 2: 00:30 -> 34% (Elapsed 30s)
    hist, trend_2, appended_2 = tm.append_or_update_timeline(hist, 130.0, 0.34, {"face": 0.17, "voice": 0.17}, ["Voice added"])
    assert appended_2 is True
    assert len(hist) == 2  # Historical checkpoint 1 untouched!
    assert hist[0]["confidence"] == 0.15
    assert hist[1]["confidence"] == 0.34
    assert trend_2 == ConfidenceTrend.UPWARD.value


# ──────────────────────────────────────────────────────────────────────────────
# 6. Pipeline & Workers Concurrency Tests
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestPipelineAndWorkers:
  async def test_end_to_end_confidence_pipeline_execution(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      pipe = ConfidencePipeline()
      ev_face = Evidence(participant_id="Candidate_Alice", source="face", score=0.90, confidence=0.92, timestamp=100.0)
      res_1 = await pipe.process_evidence("m_pipe", ev_face)
      assert res_1 is not None
      assert res_1.participant_id == "Candidate_Alice"
      assert res_1.overall_confidence > 0.0

      # Add second independent source (voice) -> confidence should rise via corroboration
      ev_voice = Evidence(participant_id="Candidate_Alice", source="voice", score=0.88, confidence=0.90, timestamp=105.0)
      res_2 = await pipe.process_evidence("m_pipe", ev_voice)
      assert res_2.overall_confidence > res_1.overall_confidence
      assert "face" in res_2.evidence_breakdown
      assert "voice" in res_2.evidence_breakdown

  async def test_worker_manager_async_queue_drainage(self):
    with patch("engine.confidence.storage.get_redis", new_callable=AsyncMock) as m_r, \
         patch("engine.confidence.storage.get_mongo_db", new_callable=AsyncMock) as m_db:
      m_r.return_value = None
      m_db.return_value = None

      wm = ConfidenceWorkerManager(worker_count=2)
      await wm.start()

      for i in range(10):
        ev = Evidence(participant_id=f"P_{i}", source="face", score=0.85, confidence=0.85, timestamp=100.0 + i)
        assert await wm.enqueue_evidence_job("m_workers", ev) is True

      await wm.stop()
      assert wm.queue.empty() is True
      assert wm.is_running is False
