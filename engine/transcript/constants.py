# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_MEETINGS_COL      = "meetings"
MONGO_TRANSCRIPTS_COL   = "transcripts"
MONGO_TURNS_COL         = "conversation_turns"
MONGO_TIMELINES_COL     = "speaker_timelines"
MONGO_EVENTS_COL        = "transcript_events"
MONGO_EVIDENCE_COL      = "transcript_evidence"   # Separate from raw transcripts
MONGO_SPEAKER_STATS_COL = "speaker_stats"          # Per-speaker cumulative metrics

# ──────────────────────────────────────────────────────────────────────────────
# Redis Key Patterns  (format with .format(meeting_id=..., speaker_id=...))
# ──────────────────────────────────────────────────────────────────────────────

# Rolling partial text for an actively-speaking participant
REDIS_KEY_PARTIAL = "scie:meeting:{meeting_id}:speaker:{speaker_id}:partial"

# Ordered list of serialised, finalised TranscriptChunk JSON strings
REDIS_KEY_FINAL_HISTORY = "scie:meeting:{meeting_id}:speaker:{speaker_id}:final_history"

# Live ParticipantTranscriptState JSON blob
REDIS_KEY_STATE = "scie:meeting:{meeting_id}:participant:{speaker_id}:transcript_state"

# Set of already-archived chunk fingerprints  (dedup guard for finalisation)
REDIS_KEY_FINALIZED_SET = "scie:meeting:{meeting_id}:speaker:{speaker_id}:finalized_set"
