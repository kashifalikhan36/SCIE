"""
Behavior Engine — SCIE
======================
Continuously observes meeting participant behavior (speech duration, response delay,
interruptions, camera toggles, screen sharing, engagement trajectory) and converts
those observations into structured behavioral features and evidence.

Does NOT use GPT or perform candidate selection. Pure analytical observation engine.
"""

from engine.behavior.pipeline import BehaviorPipeline
from engine.behavior.workers import BehaviorWorkerManager, enqueue_behavior_observation
from engine.behavior.schemas import (
    BehaviorEvidence,
    BehaviorFeatures,
    BehaviorTimelineEntry,
    ParticipantBehaviorState,
    VideoObservation,
    AudioObservation,
    TranscriptObservation,
    MetadataObservation,
)
from engine.behavior.models import (
    SpeakingMetrics,
    ResponseMetrics,
    InterruptionMetrics,
    ParticipationMetrics,
    CameraMetrics,
    ScreenShareMetrics,
    EngagementMetrics,
    EmotionMetrics,
    GazeMetrics,
)
from engine.behavior.config import behavior_config
from engine.behavior.exceptions import BehaviorEngineException

__all__ = [
    "BehaviorPipeline",
    "BehaviorWorkerManager",
    "enqueue_behavior_observation",
    "BehaviorEvidence",
    "BehaviorFeatures",
    "BehaviorTimelineEntry",
    "ParticipantBehaviorState",
    "VideoObservation",
    "AudioObservation",
    "TranscriptObservation",
    "MetadataObservation",
    "SpeakingMetrics",
    "ResponseMetrics",
    "InterruptionMetrics",
    "ParticipationMetrics",
    "CameraMetrics",
    "ScreenShareMetrics",
    "EngagementMetrics",
    "EmotionMetrics",
    "GazeMetrics",
    "behavior_config",
    "BehaviorEngineException",
]
