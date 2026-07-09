"""
Pydantic V2 schemas for the Conversation Reasoning Engine.
Defines canonical evidence output, live Redis caching models, and audit storage structures.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from engine.conversation.utils import now_ms


class ConversationEvidence(BaseModel):
  """Structured reasoning evidence output by the Conversation Reasoning Engine.

  Represents an independent semantic evaluation of a single speaker on a specific dimension
  (e.g., 'interviewer', 'candidate_behavior', 'project_discussion', etc.).

  Does NOT identify the final candidate or blend scores across different dimensions.
  """
  evidence_id: str = Field(..., description="Unique ID prefixed with CE_")
  meeting_id: str
  speaker_id: str
  evidence_type: str = Field(..., description="Specific reasoning dimension (e.g. interviewer)")
  score: float = Field(..., ge=0.0, le=1.0, description="Likelihood/intensity score on this dimension")
  confidence: float = Field(..., ge=0.0, le=1.0, description="Model certainty in the evaluation")
  reason: str = Field(..., description="Semantic justification for the score")
  supporting_quotes: List[str] = Field(default_factory=list, description="Direct utterances supporting the score")
  timestamp: int = Field(default_factory=now_ms, description="Epoch milliseconds of generation")


class ParticipantConversationState(BaseModel):
  """Live participant conversation reasoning state cached in Azure Cache for Redis.

  Holds the latest reasoning evidence map across all evaluated dimensions for a speaker.
  """
  speaker_id: str
  meeting_id: str
  latest_reasoning: Dict[str, Any] = Field(
      default_factory=dict,
      description="Mapping of evidence_type -> dictionary representation of latest ConversationEvidence"
  )
  latest_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
  conversation_summary: str = Field(default="", description="High-level summary of speaker contributions")
  last_updated: int = Field(default_factory=now_ms)


class ConversationReasoningSnapshot(BaseModel):
  """Summary snapshot of a full conversation reasoning execution pass stored in MongoDB."""
  snapshot_id: str
  meeting_id: str
  chunk_id: Optional[str] = None
  evidence_count: int
  speaker_count: int
  timestamp: int = Field(default_factory=now_ms)


class PromptHistoryRecord(BaseModel):
  """Audit log record for an individual Azure OpenAI prompt execution stored in MongoDB."""
  record_id: str
  meeting_id: str
  chunk_id: str
  prompt_type: str
  prompt_version: str
  model_version: str
  latency_ms: float
  tokens_used: int
  status: str = "SUCCESS"
  error_message: Optional[str] = None
  timestamp: int = Field(default_factory=now_ms)
