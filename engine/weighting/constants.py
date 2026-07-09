"""
Domain identifiers, evidence status enums, weighting strategy types, and Redis/MongoDB keys
for the SCIE Dynamic Weighting Engine.

(`engine/weighting/constants.py`)
"""
from enum import Enum

# ──────────────────────────────────────────────────────────────────────────────
# Domain Identifiers
# ──────────────────────────────────────────────────────────────────────────────
DOMAIN_VISUAL = "visual"
DOMAIN_VOICE = "voice"
DOMAIN_TRANSCRIPT = "transcript"
DOMAIN_CONVERSATION = "conversation"
DOMAIN_BEHAVIOR = "behavior"
DOMAIN_IDENTITY = "identity"
DOMAIN_METADATA = "metadata"

ALL_DOMAINS = (
    DOMAIN_VISUAL,
    DOMAIN_VOICE,
    DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION,
    DOMAIN_BEHAVIOR,
    DOMAIN_IDENTITY,
    DOMAIN_METADATA,
)


# ──────────────────────────────────────────────────────────────────────────────
# Evidence Availability Status Enums
# ──────────────────────────────────────────────────────────────────────────────
class EvidenceAvailability(str, Enum):
  """Status representing whether an evidence domain can actively contribute weight."""
  AVAILABLE = "AVAILABLE"
  UNAVAILABLE = "UNAVAILABLE"
  DEGRADED = "DEGRADED"
  INVALID = "INVALID"
  UNKNOWN = "UNKNOWN"


# ──────────────────────────────────────────────────────────────────────────────
# Strategy Type Enums
# ──────────────────────────────────────────────────────────────────────────────
class WeightingStrategyType(str, Enum):
  """Configurable weighting strategies supporting dynamic meeting contexts."""
  DEFAULT = "DEFAULT"
  INTERVIEW_STARTED = "INTERVIEW_STARTED"
  INTERVIEW_IN_PROGRESS = "INTERVIEW_IN_PROGRESS"
  CODING_ROUND = "CODING_ROUND"
  BEHAVIOR_ROUND = "BEHAVIOR_ROUND"
  CAMERA_OFF = "CAMERA_OFF"
  VOICE_ONLY = "VOICE_ONLY"
  VIDEO_ONLY = "VIDEO_ONLY"
  METADATA_ONLY = "METADATA_ONLY"


# ──────────────────────────────────────────────────────────────────────────────
# Redis Keys
# ──────────────────────────────────────────────────────────────────────────────
REDIS_KEY_LATEST_WEIGHTS = "scie:weighting:{meeting_id}:participant:{participant_id}:latest"
REDIS_KEY_MEETING_WEIGHT_PARTICIPANTS = "scie:weighting:{meeting_id}:participants"
REDIS_KEY_PARTICIPANT_STATE_UPSTREAM = "scie:meeting:{meeting_id}:participant:{participant_id}:state"


# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collections
# ──────────────────────────────────────────────────────────────────────────────
MONGO_COL_WEIGHT_PROFILES = "weight_profiles"
MONGO_COL_WEIGHT_HISTORY = "weight_history"
MONGO_COL_STRATEGY_CHANGES = "strategy_changes"
MONGO_COL_QUALITY_SCORES = "quality_scores"
