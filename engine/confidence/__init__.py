"""
Sherlock Candidate Identification System — Confidence Engine (`engine/confidence/`).

The production-ready **Confidence Engine** is responsible for continuously calculating,
updating, maintaining, and explaining the confidence score `[0.0, 1.0]` for every participant
as independent evidence signals (`face`, `voice`, `identity`, `conversation`, `behavior`,
`transcript`, `emotion`, `gaze`) arrive from all other SCIE engines.

Does NOT directly process audio/video or call AI/GPT models.
Exposes clean, explainable `ConfidenceResult` structures required by downstream dashboard and selection components.
(`engine/confidence/__init__.py`)
"""

from engine.confidence.constants import (
    EvidenceSource, ConfidenceTrend, NormalizationStrategyType, CalculationStrategyType,
    ALL_EVIDENCE_SOURCES
)
from engine.confidence.config import confidence_config, ConfidenceEngineSettings
from engine.confidence.exceptions import (
    ConfidenceEngineException, ConfidenceValidationError, ConfidenceNormalizationError,
    ConfidenceWeightError, ConfidenceCalculationError, ConfidenceStorageError
)
from engine.confidence.models import (
    RawEvidenceItem, NormalizedEvidenceItem, ConfidenceCalculationContext, TimelineSnapshot
)
from engine.confidence.schemas import (
    Evidence, ParticipantConfidence, ConfidenceResult, ConfidenceEvent
)
from engine.confidence.validator import EvidenceValidator
from engine.confidence.normalizer import (
    EvidenceNormalizer, ScoreNormalizationStrategy,
    LinearNormalizationStrategy, SigmoidNormalizationStrategy,
    MinMaxNormalizationStrategy, ZScoreNormalizationStrategy
)
from engine.confidence.weighting import WeightManager
from engine.confidence.dynamic_weighting import DynamicConfidenceWeighting
from engine.confidence.calculator import (
    ConfidenceCalculator, ConfidenceStrategy,
    WeightedAverageStrategy, BayesianStrategy, LearnedMetaModelStrategy
)
from engine.confidence.timeline import ConfidenceTimelineManager
from engine.confidence.provider import ConfidenceProvider
from engine.confidence.participant_state import ConfidenceStateManager
from engine.confidence.storage import ConfidenceStorageManager
from engine.confidence.pipeline import ConfidencePipeline
from engine.confidence.workers import ConfidenceWorkerManager, get_confidence_worker_manager

__all__ = [
    "EvidenceSource", "ConfidenceTrend", "NormalizationStrategyType", "CalculationStrategyType",
    "ALL_EVIDENCE_SOURCES", "confidence_config", "ConfidenceEngineSettings",
    "ConfidenceEngineException", "ConfidenceValidationError", "ConfidenceNormalizationError",
    "ConfidenceWeightError", "ConfidenceCalculationError", "ConfidenceStorageError",
    "RawEvidenceItem", "NormalizedEvidenceItem", "ConfidenceCalculationContext", "TimelineSnapshot",
    "Evidence", "ParticipantConfidence", "ConfidenceResult", "ConfidenceEvent",
    "EvidenceValidator", "EvidenceNormalizer", "ScoreNormalizationStrategy",
    "LinearNormalizationStrategy", "SigmoidNormalizationStrategy",
    "MinMaxNormalizationStrategy", "ZScoreNormalizationStrategy",
    "WeightManager", "DynamicConfidenceWeighting",
    "ConfidenceCalculator", "ConfidenceStrategy",
    "WeightedAverageStrategy", "BayesianStrategy", "LearnedMetaModelStrategy",
    "ConfidenceTimelineManager", "ConfidenceProvider", "ConfidenceStateManager",
    "ConfidenceStorageManager", "ConfidencePipeline",
    "ConfidenceWorkerManager", "get_confidence_worker_manager",
]
