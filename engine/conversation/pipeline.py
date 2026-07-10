"""
Conversation Reasoning Engine Pipeline.

Orchestrates the complete end-to-end reasoning workflow:
1. Load transcript turns (from MongoDB / Redis or provided directly).
2. Segment turns into chronological chunks bounded by turns/time.
3. Execute multi-prompt Azure OpenAI semantic reasoning with SHA-256 caching.
4. Synthesize canonical ConversationEvidence objects.
5. Update live speaker reasoning state in Azure Cache for Redis.
6. Persist audit snapshots and history across all 4 MongoDB collections.
"""
from typing import List, Optional
from engine.transcript.schemas import ConversationTurn
from engine.conversation.transcript_loader import ConversationTranscriptLoader
from engine.conversation.conversation_analyzer import ConversationAnalyzer
from engine.conversation.reasoning_engine import ConversationReasoningEngine
from engine.conversation.evidence_provider import ConversationEvidenceProvider
from engine.conversation.participant_state import ConversationStateManager
from engine.conversation.storage import ConversationStorageManager
from engine.conversation.schemas import ConversationEvidence
from engine.conversation.exceptions import PipelineExecutionError
from engine.conversation.logger import logger, measure_latency


class ConversationPipeline:
  """Top-level orchestration pipeline for the Conversation Reasoning Engine."""

  def __init__(self):
    self._loader = ConversationTranscriptLoader()
    self._analyzer = ConversationAnalyzer()
    self._reasoner = ConversationReasoningEngine()
    self._provider = ConversationEvidenceProvider()
    self._state_mgr = ConversationStateManager()
    self._storage = ConversationStorageManager()

  @measure_latency("conversation_pipeline.process")
  async def process(
      self,
      meeting_id: str,
      turns: Optional[List[ConversationTurn]] = None,
      prompt_types: Optional[List[str]] = None
  ) -> List[ConversationEvidence]:
    """Execute complete conversation reasoning pass for the specified meeting."""
    try:
      # 1. Load transcript turns
      target_turns = turns if turns is not None else await self._loader.load_turns(meeting_id)
      if not target_turns:
        logger.info(f"ConversationPipeline: No transcript turns found for meeting={meeting_id}. Skipping reasoning.")
        return []

      logger.debug(f"ConversationPipeline: Processing {len(target_turns)} turns for {meeting_id}")

      # 2. Segment into chunks
      chunks = self._analyzer.chunk_conversation(target_turns)
      if not chunks:
        return []

      logger.debug(f"ConversationPipeline: Formatted {len(chunks)} conversation chunks.")

      # 3. Run semantic reasoning prompts across chunks
      exec_results = await self._reasoner.reason_over_chunks(chunks, prompt_types=prompt_types)

      # 4. Synthesize canonical ConversationEvidence
      evidence_list = self._provider.provide(exec_results, meeting_id)

      # 5. Save prompt execution history to MongoDB
      for res in exec_results:
        await self._storage.save_prompt_history(
            meeting_id=meeting_id,
            chunk_id=res.chunk_id,
            prompt_type=res.prompt_type,
            prompt_version="1.0",
            model_version=res.model_version,
            latency_ms=res.latency_ms,
            tokens_used=res.tokens_used,
            status="SUCCESS" if res.evaluations or res.model_version == "cached" else "ERROR",
            error_message=str(res.raw_response.get("error")) if "error" in res.raw_response else None
        )

      if not evidence_list:
        logger.info(f"ConversationPipeline: No significant evidence items synthesized for {meeting_id}")
        return []

      # 6. Update live Redis participant states and save reasoning history
      states = self._provider.build_participant_states(evidence_list, meeting_id)
      for st in states:
        await self._state_mgr.save_state(st)
        await self._storage.save_reasoning_history(
            meeting_id=meeting_id,
            speaker_id=st.speaker_id,
            evidence_map=st.latest_reasoning,
            confidence=st.latest_confidence,
            summary=st.conversation_summary,
            timestamp=st.last_updated
        )

      # 7. Persist evidence items and overall pass snapshot to MongoDB
      await self._storage.save_evidence_batch(evidence_list)
      await self._storage.save_reasoning_snapshot(
          meeting_id=meeting_id,
          evidence_count=len(evidence_list),
          speaker_count=len(states)
      )

      # 8. Enqueue to FusionEngine
      try:
          from engine.fusion.workers import enqueue_fusion_evidence
          from engine.fusion.constants import DOMAIN_CONVERSATION
          for ev in evidence_list:
              await enqueue_fusion_evidence(
                  evidence_obj=ev,
                  source_type=DOMAIN_CONVERSATION,
                  speaker_id=ev.speaker_id,
                  score=ev.score,
                  reliability=ev.confidence
              )
      except Exception as fe:
          logger.error(f"ConversationPipeline: Failed to enqueue to FusionEngine: {fe}")

      logger.info(
          f"ConversationPipeline: Successfully processed {meeting_id} — produced {len(evidence_list)} "
          f"evidence items across {len(states)} speakers."
      )
      return evidence_list

    except Exception as exc:
      logger.error(f"ConversationPipeline: Processing failed for {meeting_id}: {exc}", exc_info=True)
      if isinstance(exc, PipelineExecutionError):
        raise
      raise PipelineExecutionError(f"Unexpected pipeline failure: {exc}") from exc
