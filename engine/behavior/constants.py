# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_BEHAVIOR_EVENTS_COL     = "behavior_events"
MONGO_BEHAVIOR_METRICS_COL    = "behavior_metrics"
MONGO_PARTICIPANT_TIMELINES_COL = "participant_timelines"
MONGO_ENGAGEMENT_HISTORY_COL  = "engagement_history"
MONGO_MEETING_STATISTICS_COL  = "meeting_statistics"

# ──────────────────────────────────────────────────────────────────────────────
# Azure Cache for Redis Key Patterns
# Format with .format(meeting_id=..., participant_id=...)
# ──────────────────────────────────────────────────────────────────────────────

# Live behavior state for a single participant
REDIS_KEY_BEHAVIOR_STATE = "scie:meeting:{meeting_id}:behavior:{participant_id}:state"

# Chronological behavior timeline list for a participant
REDIS_KEY_BEHAVIOR_TIMELINE = "scie:meeting:{meeting_id}:behavior:{participant_id}:timeline"

# Set of all participants tracked in this meeting by the behavior engine
REDIS_KEY_MEETING_BEHAVIORS = "scie:meeting:{meeting_id}:behaviors"

# ──────────────────────────────────────────────────────────────────────────────
# Engagement Levels & Event Types
# ──────────────────────────────────────────────────────────────────────────────

ENGAGEMENT_LOW    = "LOW"
ENGAGEMENT_MEDIUM = "MEDIUM"
ENGAGEMENT_HIGH   = "HIGH"

EVENT_JOIN            = "JOIN"
EVENT_LEAVE           = "LEAVE"
EVENT_CAMERA_ON       = "CAMERA_ON"
EVENT_CAMERA_OFF      = "CAMERA_OFF"
EVENT_MIC_ON          = "MIC_ON"
EVENT_MIC_OFF         = "MIC_OFF"
EVENT_SCREEN_SHARE_ON = "SCREEN_SHARE_ON"
EVENT_SCREEN_SHARE_OFF = "SCREEN_SHARE_OFF"
EVENT_SPEAKING_START  = "SPEAKING_START"
EVENT_SPEAKING_END    = "SPEAKING_END"
EVENT_INTERRUPTION    = "INTERRUPTION"
EVENT_QUESTION_ASKED  = "QUESTION_ASKED"
