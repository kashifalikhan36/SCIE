"""
Constants and Enums for the SCIE Confidence Engine (`engine/confidence/`).

Defines evidence source identifiers, confidence trend classifications,
normalization strategy keys, calculation strategy keys, Redis key patterns,
and MongoDB collection names.
(`engine/confidence/constants.py`)
"""
from enum import Enum
from typing import Set


class EvidenceSource(str, Enum):
  """Recognized upstream evidence source identifiers."""
  FACE = "face"
  VOICE = "voice"
  IDENTITY = "identity"
  CONVERSATION = "conversation"
  BEHAVIOR = "behavior"
  TRANSCRIPT = "transcript"
  EMOTION = "emotion"  # Future engine
  GAZE = "gaze"        # Future engine


# Primary domain set for quick lookup
ALL_EVIDENCE_SOURCES: Set[str] = {
    EvidenceSource.FACE.value,
    EvidenceSource.VOICE.value,
    EvidenceSource.IDENTITY.value,
    EvidenceSource.CONVERSATION.value,
    EvidenceSource.BEHAVIOR.value,
    EvidenceSource.TRANSCRIPT.value,
    EvidenceSource.EMOTION.value,
    EvidenceSource.GAZE.value,
}


class ConfidenceTrend(str, Enum):
  """Classification of participant confidence trajectory across time."""
  UPWARD = "UPWARD"
  DOWNWARD = "DOWNWARD"
  STABLE = "STABLE"
  RECOVERING = "RECOVERING"


class NormalizationStrategyType(str, Enum):
  """Supported score normalization strategies [0.0 -> 1.0]."""
  LINEAR = "linear"
  SIGMOID = "sigmoid"
  ZSCORE = "zscore"
  MINMAX = "minmax"


class CalculationStrategyType(str, Enum):
  """Supported confidence calculation algorithms."""
  WEIGHTED_AVERAGE = "weighted_average"
  BAYESIAN = "bayesian"
  LEARNED_META_MODEL = "learned_meta_model"


# ──────────────────────────────────────────────────────────────────────────────
# Redis Key Patterns
# ──────────────────────────────────────────────────────────────────────────────
REDIS_KEY_PARTICIPANT_CONFIDENCE = "participant:confidence:{meeting_id}:{participant_id}"
REDIS_KEY_PARTICIPANT_WEIGHTS = "participant:weights:{meeting_id}:{participant_id}"
REDIS_KEY_PARTICIPANT_ACTIVE_EVIDENCE = "participant:active_evidence:{meeting_id}:{participant_id}"
REDIS_KEY_PARTICIPANT_LATEST_TIMESTAMP = "participant:latest_timestamp:{meeting_id}:{participant_id}"
REDIS_KEY_MEETING_CONFIDENCE_SET = "meeting:confidence:participants:{meeting_id}"

# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names (Append-Only)
# ──────────────────────────────────────────────────────────────────────────────
MONGO_COL_CONFIDENCE_HISTORY = "confidence_history"
MONGO_COL_CONFIDENCE_EVENTS = "confidence_events"
MONGO_COL_PARTICIPANT_CONFIDENCE = "participant_confidence"
MONGO_COL_MEETING_CONFIDENCE = "meeting_confidence"
