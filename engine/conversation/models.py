"""
Internal data models for the Conversation Reasoning Engine.
Used across chunking, prompt execution, and internal pipeline processing.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class ConversationChunk:
  """A bounded slice of conversation turns formatted for prompt evaluation."""
  chunk_id: str
  meeting_id: str
  turn_index_start: int
  turn_index_end: int
  start_time: float
  end_time: float
  turn_count: int
  formatted_text: str
  speakers: List[str] = field(default_factory=list)


@dataclass
class PromptEvaluationItem:
  """Raw speaker evaluation extracted from GPT structured JSON output."""
  speaker_id: str
  score: float
  confidence: float
  reason: str
  supporting_quotes: List[str] = field(default_factory=list)


@dataclass
class PromptExecutionResult:
  """Result of executing a single reasoning prompt across a conversation chunk."""
  prompt_type: str
  meeting_id: str
  chunk_id: str
  evaluations: List[PromptEvaluationItem] = field(default_factory=list)
  model_version: str = ""
  latency_ms: float = 0.0
  tokens_used: int = 0
  raw_response: Dict[str, Any] = field(default_factory=dict)
