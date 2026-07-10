"""
Evidence Provider for the Conversation Reasoning Engine.

Responsibilities:
- Transform raw PromptExecutionResult objects into canonical, validated ConversationEvidence models.
- Preserve exact scores, confidences, justifications, and supporting quotes.
- NEVER combine scores across dimensions or determine the final candidate.
"""
from typing import List, Dict, Any
from engine.conversation.schemas import ConversationEvidence, ParticipantConversationState
from engine.conversation.models import PromptExecutionResult
from engine.conversation.utils import generate_evidence_id, clamp, now_ms
from engine.conversation.logger import logger


class ConversationEvidenceProvider:
  """Synthesizes raw prompt evaluations into standardized ConversationEvidence models."""

  @classmethod
  def provide(
      cls,
      execution_results: List[PromptExecutionResult],
      meeting_id: str
  ) -> List[ConversationEvidence]:
    """Convert raw PromptExecutionResults into a flat list of validated ConversationEvidence objects."""
    evidence_list: List[ConversationEvidence] = []
    if not execution_results:
      return evidence_list

    for result in execution_results:
      for eval_item in result.evaluations:
        spk = eval_item.speaker_id.strip()
        if not spk or spk.lower() == "unknown":
          continue

        score = round(clamp(eval_item.score, 0.0, 1.0), 4)
        conf = round(clamp(eval_item.confidence, 0.0, 1.0), 4)

        ev = ConversationEvidence(
            evidence_id=generate_evidence_id(),
            meeting_id=meeting_id,
            speaker_id=spk,
            evidence_type=result.prompt_type,
            score=score,
            confidence=conf,
            reason=eval_item.reason or f"Evaluated for {result.prompt_type}",
            supporting_quotes=eval_item.supporting_quotes or [],
            extracted_name=getattr(eval_item, "extracted_name", None),
            timestamp=now_ms()
        )
        evidence_list.append(ev)

    logger.debug(f"EvidenceProvider: Produced {len(evidence_list)} canonical ConversationEvidence items for {meeting_id}")
    return evidence_list

  @classmethod
  def build_participant_states(
      cls,
      evidence_list: List[ConversationEvidence],
      meeting_id: str
  ) -> List[ParticipantConversationState]:
    """Group ConversationEvidence items by speaker into ParticipantConversationState models for Redis caching."""
    speaker_map: Dict[str, Dict[str, ConversationEvidence]] = {}

    for ev in evidence_list:
      if ev.speaker_id not in speaker_map:
        speaker_map[ev.speaker_id] = {}
      # If multiple chunks produced evidence for the same type, keep the most recent / highest confidence one
      existing = speaker_map[ev.speaker_id].get(ev.evidence_type)
      if existing is None or ev.confidence >= existing.confidence:
        speaker_map[ev.speaker_id][ev.evidence_type] = ev

    states: List[ParticipantConversationState] = []
    for spk, type_map in speaker_map.items():
      # Calculate latest average confidence across available dimensions for this speaker
      avg_conf = sum(e.confidence for e in type_map.values()) / len(type_map) if type_map else 0.0
      # Create summary
      top_traits = sorted(type_map.values(), key=lambda e: e.score * e.confidence, reverse=True)[:3]
      summary_str = ", ".join(f"{e.evidence_type}({e.score:.2f})" for e in top_traits) if top_traits else "Evaluated"

      serialized_map = {k: v.model_dump() for k, v in type_map.items()}

      state = ParticipantConversationState(
          speaker_id=spk,
          meeting_id=meeting_id,
          latest_reasoning=serialized_map,
          latest_confidence=round(avg_conf, 4),
          conversation_summary=f"Top roles/traits: {summary_str}",
          last_updated=now_ms()
      )
      states.append(state)

    return states
