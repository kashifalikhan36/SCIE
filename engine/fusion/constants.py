"""
Constants for the Evidence Fusion Engine (`engine/fusion/`).

Defines evidence status enums, domain source identifiers, MongoDB collection names,
and Azure Cache for Redis key patterns.
"""
from enum import Enum


# ──────────────────────────────────────────────────────────────────────────────
# Evidence Status Enumerations
# ──────────────────────────────────────────────────────────────────────────────

class EvidenceStatus(str, Enum):
  """Status representing the state and availability of a specific evidence signal.

  Note: UNAVAILABLE or FAILED signals must NEVER be treated as negative scores.
  """
  AVAILABLE = "AVAILABLE"
  UNAVAILABLE = "UNAVAILABLE"
  STALE = "STALE"
  FAILED = "FAILED"


# ──────────────────────────────────────────────────────────────────────────────
# Evidence Source / Domain Identifiers
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_IDENTITY = "identity"
DOMAIN_VISUAL = "visual"
DOMAIN_VOICE = "voice"
DOMAIN_BEHAVIOR = "behavior"
DOMAIN_CONVERSATION = "conversation"
DOMAIN_TRANSCRIPT = "transcript"

ALL_DOMAINS = (
    DOMAIN_IDENTITY,
    DOMAIN_VISUAL,
    DOMAIN_VOICE,
    DOMAIN_BEHAVIOR,
    DOMAIN_CONVERSATION,
    DOMAIN_TRANSCRIPT,
)


# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_MEETINGS_COL = "meetings"
MONGO_PARTICIPANT_STATES_COL = "participant_states"
MONGO_PARTICIPANT_SCORES_COL = "participant_scores"
MONGO_CONFIDENCE_HISTORY_COL = "confidence_history"
MONGO_FUSION_EVENTS_COL = "fusion_events"
MONGO_RANKING_HISTORY_COL = "ranking_history"
MONGO_EXPLANATIONS_COL = "explanations"

ALL_FUSION_COLLECTIONS = (
    MONGO_MEETINGS_COL,
    MONGO_PARTICIPANT_STATES_COL,
    MONGO_PARTICIPANT_SCORES_COL,
    MONGO_CONFIDENCE_HISTORY_COL,
    MONGO_FUSION_EVENTS_COL,
    MONGO_RANKING_HISTORY_COL,
    MONGO_EXPLANATIONS_COL,
)


# ──────────────────────────────────────────────────────────────────────────────
# Azure Cache for Redis Key Patterns
# Format with .format(meeting_id=..., participant_id=...)
# ──────────────────────────────────────────────────────────────────────────────

# Live participant fusion state for a single participant
REDIS_KEY_PARTICIPANT_STATE = "scie:meeting:{meeting_id}:fusion:participant:{participant_id}:state"

# Live overall meeting fusion state
REDIS_KEY_MEETING_STATE = "scie:meeting:{meeting_id}:fusion:state"

# Confidence score history list for a participant
REDIS_KEY_CONFIDENCE_HISTORY = "scie:meeting:{meeting_id}:fusion:confidence_history:{participant_id}"

# Latest ranking result across all meeting participants
REDIS_KEY_LATEST_RANKING = "scie:meeting:{meeting_id}:fusion:ranking"

# Set of all active participant IDs tracked in this meeting
REDIS_KEY_ACTIVE_PARTICIPANTS = "scie:meeting:{meeting_id}:fusion:participants"

# High-frequency active evidence item cache per participant
REDIS_KEY_EVIDENCE_CACHE = "scie:meeting:{meeting_id}:fusion:cache:{participant_id}"
