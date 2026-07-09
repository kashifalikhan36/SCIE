"""
Sherlock Candidate Identification System — Dynamic Weighting Engine (`engine/weighting/`)

Produces optimal contribution weights across 7 independent evidence sources (`Visual`, `Voice`,
`Transcript`, `Conversation`, `Behavior`, `Identity`, `Metadata`) dynamically tailored to
real-time meeting context, availability status, and multi-faceted quality metrics.

(`engine/weighting/__init__.py`)
"""
from engine.weighting.config import weighting_config, WeightingEngineSettings
from engine.weighting.constants import (
    EvidenceAvailability, WeightingStrategyType,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA,
    ALL_DOMAINS
)
from engine.weighting.exceptions import (
    WeightingEngineException, EvidenceValidationError,
    QualityEvaluationError, StrategyEvaluationError,
    WeightNormalizationError, StorageError
)
from engine.weighting.schemas import (
    UpstreamParticipantState, EvidencePayloads,
    QualityScores, DynamicWeightProfile, ParticipantWeightState
)
from engine.weighting.engine import DynamicWeightingEngine
from engine.weighting.pipeline import WeightingPipeline
from engine.weighting.workers import WeightingWorkerManager, get_worker_manager, enqueue_weighting_job

__all__ = [
    "weighting_config",
    "WeightingEngineSettings",
    "EvidenceAvailability",
    "WeightingStrategyType",
    "DOMAIN_VISUAL",
    "DOMAIN_VOICE",
    "DOMAIN_TRANSCRIPT",
    "DOMAIN_CONVERSATION",
    "DOMAIN_BEHAVIOR",
    "DOMAIN_IDENTITY",
    "DOMAIN_METADATA",
    "ALL_DOMAINS",
    "WeightingEngineException",
    "EvidenceValidationError",
    "QualityEvaluationError",
    "StrategyEvaluationError",
    "WeightNormalizationError",
    "StorageError",
    "UpstreamParticipantState",
    "EvidencePayloads",
    "QualityScores",
    "DynamicWeightProfile",
    "ParticipantWeightState",
    "DynamicWeightingEngine",
    "WeightingPipeline",
    "WeightingWorkerManager",
    "get_worker_manager",
    "enqueue_weighting_job",
]
