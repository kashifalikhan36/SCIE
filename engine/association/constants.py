# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_PARTICIPANT_IDENTITY_COL = "participant_identity"
MONGO_ASSOCIATION_HISTORY_COL  = "association_history"
MONGO_IDENTITY_EVENTS_COL      = "identity_events"
MONGO_PARTICIPANT_TIMELINE_COL = "participant_timeline"
MONGO_IDENTITY_CONFIDENCE_COL  = "identity_confidence"

# ──────────────────────────────────────────────────────────────────────────────
# Azure Cache for Redis Key Patterns
# Format with .format(meeting_id=..., participant_id=..., track_id=..., speaker_id=...)
# ──────────────────────────────────────────────────────────────────────────────

# Live state of a single participant
REDIS_KEY_PARTICIPANT_STATE = "scie:meeting:{meeting_id}:participant:{participant_id}:state"

# Set of all participant_ids currently in the meeting
REDIS_KEY_MEETING_PARTICIPANTS = "scie:meeting:{meeting_id}:participants"

# Reverse lookup map: track_id -> participant_id
REDIS_KEY_TRACK_MAP = "scie:meeting:{meeting_id}:map:track:{track_id}"

# Reverse lookup map: speaker_id -> participant_id
REDIS_KEY_SPEAKER_MAP = "scie:meeting:{meeting_id}:map:speaker:{speaker_id}"
