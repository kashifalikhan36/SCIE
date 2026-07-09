# ──────────────────────────────────────────────────────────────────────────────
# MongoDB Collection Names
# ──────────────────────────────────────────────────────────────────────────────

MONGO_CONVERSATION_REASONING_COL = "conversation_reasoning"
MONGO_CONVERSATION_EVIDENCE_COL  = "conversation_evidence"
MONGO_REASONING_HISTORY_COL      = "reasoning_history"
MONGO_PROMPT_HISTORY_COL         = "prompt_history"

# ──────────────────────────────────────────────────────────────────────────────
# Azure Cache for Redis Key Patterns
# Format with .format(meeting_id=..., speaker_id=..., prompt_hash=...)
# ──────────────────────────────────────────────────────────────────────────────

# Live conversation reasoning state for a single speaker
REDIS_KEY_CONVERSATION_STATE = "scie:meeting:{meeting_id}:conversation:{speaker_id}:state"

# Cache key for a specific prompt + transcript slice hash
REDIS_KEY_CONVERSATION_CACHE = "scie:meeting:{meeting_id}:conversation:cache:{prompt_hash}"

# Set of all speaker IDs tracked in this meeting by the conversation engine
REDIS_KEY_MEETING_SPEAKERS = "scie:meeting:{meeting_id}:conversation:speakers"

# ──────────────────────────────────────────────────────────────────────────────
# Evidence Types Emitted by Conversation Reasoning Engine
# ──────────────────────────────────────────────────────────────────────────────

EVIDENCE_INTERVIEWER          = "interviewer"
EVIDENCE_CANDIDATE_BEHAVIOR   = "candidate_behavior"
EVIDENCE_PROJECT_DISCUSSION   = "project_discussion"
EVIDENCE_EXPERIENCE_DISCUSSION = "experience_discussion"
EVIDENCE_TECHNICAL_ANSWER     = "technical_answer"
EVIDENCE_QUESTION_RECEIVER    = "question_receiver"
EVIDENCE_QUESTION_ASKER       = "question_asker"
EVIDENCE_OBSERVER             = "observer"
EVIDENCE_SELF_INTRODUCTION    = "self_introduction"
EVIDENCE_CODING_DISCUSSION    = "coding_discussion"
EVIDENCE_MEETING_LEADER       = "meeting_leader"
EVIDENCE_INSUFFICIENT         = "insufficient_evidence"

ALL_EVIDENCE_TYPES = (
    EVIDENCE_INTERVIEWER,
    EVIDENCE_CANDIDATE_BEHAVIOR,
    EVIDENCE_PROJECT_DISCUSSION,
    EVIDENCE_EXPERIENCE_DISCUSSION,
    EVIDENCE_TECHNICAL_ANSWER,
    EVIDENCE_QUESTION_RECEIVER,
    EVIDENCE_QUESTION_ASKER,
    EVIDENCE_OBSERVER,
    EVIDENCE_SELF_INTRODUCTION,
    EVIDENCE_CODING_DISCUSSION,
    EVIDENCE_MEETING_LEADER,
    EVIDENCE_INSUFFICIENT,
)
