"""
Evidence Fusion Engine — SCIE
=============================
Central intelligence component responsible for combining evidence from all upstream engines
(Identity, Visual, Voice, Behavior, Conversation, Transcript) to calculate continuously
improving multi-signal confidence scores over time, rank participants, and generate explainable
rule-based justifications.

Does NOT perform audio/video/Whisper/MediaPipe/InsightFace or GPT calls directly.
"""

from engine.fusion.pipeline import FusionPipeline, fusion_pipeline
from engine.fusion.workers import FusionWorkerManager, enqueue_fusion_evidence
from engine.fusion.schemas import (
    IncomingEvidence,
    ParticipantState,
    ParticipantScore,
    RankingResult,
    Explanation,
    ConfidenceHistoryItem,
    FusionResult
)
from engine.fusion.constants import (
    EvidenceStatus,
    DOMAIN_IDENTITY,
    DOMAIN_VISUAL,
    DOMAIN_VOICE,
    DOMAIN_BEHAVIOR,
    DOMAIN_CONVERSATION,
    DOMAIN_TRANSCRIPT
)
from engine.fusion.config import fusion_config
from engine.fusion.exceptions import (
    FusionEngineException,
    EvidenceAggregationError,
    WeightCalculationError,
    ScoringError,
    ConfidenceCalculationError,
    RankingError,
    ExplanationGenerationError,
    FusionStorageError,
    FusionStateError,
    DuplicateEvidenceError
)

__all__ = [
    "FusionPipeline",
    "fusion_pipeline",
    "FusionWorkerManager",
    "enqueue_fusion_evidence",
    "IncomingEvidence",
    "ParticipantState",
    "ParticipantScore",
    "RankingResult",
    "Explanation",
    "ConfidenceHistoryItem",
    "FusionResult",
    "EvidenceStatus",
    "DOMAIN_IDENTITY",
    "DOMAIN_VISUAL",
    "DOMAIN_VOICE",
    "DOMAIN_BEHAVIOR",
    "DOMAIN_CONVERSATION",
    "DOMAIN_TRANSCRIPT",
    "fusion_config",
    "FusionEngineException",
    "EvidenceAggregationError",
    "WeightCalculationError",
    "ScoringError",
    "ConfidenceCalculationError",
    "RankingError",
    "ExplanationGenerationError",
    "FusionStorageError",
    "FusionStateError",
    "DuplicateEvidenceError",
]
