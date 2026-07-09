"""
Conversation Reasoning Engine (`engine/conversation/`).

Responsible for semantic reasoning across structured conversation transcripts
using Azure OpenAI Foundry (`GPT-5.5`).

Emits canonical ``ConversationEvidence`` evaluations without combining scores
or determining the final candidate.
"""
from engine.conversation.pipeline import ConversationPipeline
from engine.conversation.workers import ConversationWorkerManager, enqueue_conversation_reasoning
from engine.conversation.schemas import ConversationEvidence, ParticipantConversationState
from engine.conversation.models import ConversationChunk, PromptExecutionResult
from engine.conversation.config import conversation_config
from engine.conversation.constants import (
    EVIDENCE_INTERVIEWER, EVIDENCE_CANDIDATE_BEHAVIOR, EVIDENCE_PROJECT_DISCUSSION,
    EVIDENCE_EXPERIENCE_DISCUSSION, EVIDENCE_TECHNICAL_ANSWER, EVIDENCE_QUESTION_RECEIVER,
    EVIDENCE_QUESTION_ASKER, EVIDENCE_OBSERVER, EVIDENCE_SELF_INTRODUCTION,
    EVIDENCE_CODING_DISCUSSION, EVIDENCE_MEETING_LEADER, EVIDENCE_INSUFFICIENT,
)

__all__ = [
    "ConversationPipeline",
    "ConversationWorkerManager",
    "enqueue_conversation_reasoning",
    "ConversationEvidence",
    "ParticipantConversationState",
    "ConversationChunk",
    "PromptExecutionResult",
    "conversation_config",
    "EVIDENCE_INTERVIEWER",
    "EVIDENCE_CANDIDATE_BEHAVIOR",
    "EVIDENCE_PROJECT_DISCUSSION",
    "EVIDENCE_EXPERIENCE_DISCUSSION",
    "EVIDENCE_TECHNICAL_ANSWER",
    "EVIDENCE_QUESTION_RECEIVER",
    "EVIDENCE_QUESTION_ASKER",
    "EVIDENCE_OBSERVER",
    "EVIDENCE_SELF_INTRODUCTION",
    "EVIDENCE_CODING_DISCUSSION",
    "EVIDENCE_MEETING_LEADER",
    "EVIDENCE_INSUFFICIENT",
]
