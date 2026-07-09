# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_IDENTITY_EVIDENCE_COL     = "identity_evidence"
MONGO_IDENTITY_MATCHES_COL      = "identity_matches"
MONGO_PARTICIPANT_IDENTITY_COL  = "identity_participant_profiles"
MONGO_IDENTITY_EVENTS_COL       = "identity_events"

# ──────────────────────────────────────────────────────────────────────────────
# Azure Cache for Redis Key Patterns
# Format with .format(meeting_id=..., participant_id=...)
# ──────────────────────────────────────────────────────────────────────────────

# Live identity state for a single participant
REDIS_KEY_IDENTITY_STATE = "scie:meeting:{meeting_id}:identity:{participant_id}:state"

# Set of all participants tracked in this meeting by the identity engine
REDIS_KEY_IDENTITY_PARTICIPANTS = "scie:meeting:{meeting_id}:identity:participants"

# Embedding cache: text hash -> serialized embedding vector (JSON list)
REDIS_KEY_EMBEDDING_CACHE = "scie:embedding:cache:{text_hash}"
