"""
Conversation Reasoning Engine core executor.

Responsibilities:
- Run multiple independent reasoning prompts across conversation chunks.
- Check Redis SHA-256 transcript cache before executing any prompt to avoid redundant Azure OpenAI calls.
- Aggregate prompt evaluation results into flat lists of PromptExecutionResult objects.
- NEVER combine scores or determine the final candidate.
"""
import asyncio
from typing import List, Optional
from engine.conversation.azure_client import ConversationAzureClient
from engine.conversation.prompts import ConversationPrompts
from engine.conversation.cache import ConversationCache
from engine.conversation.constants import ALL_EVIDENCE_TYPES
from engine.conversation.models import ConversationChunk, PromptEvaluationItem, PromptExecutionResult
from engine.conversation.utils import hash_transcript
from engine.conversation.exceptions import ReasoningExecutionError
from engine.conversation.logger import logger, measure_latency


class ConversationReasoningEngine:
  """Executes targeted semantic reasoning prompts over conversation chunks."""

  def __init__(self, cache: Optional[ConversationCache] = None):
    self._client = ConversationAzureClient.get_instance()
    self._cache = cache or ConversationCache()

  @measure_latency("reasoning_engine.execute_prompt")
  async def execute_prompt_on_chunk(
      self, chunk: ConversationChunk, prompt_type: str
  ) -> PromptExecutionResult:
    """Run a single semantic prompt on a single chunk, utilizing Redis cache when possible."""
    chunk_hash = hash_transcript(chunk.formatted_text)
    cached = await self._cache.get_cached_evaluation(chunk.meeting_id, prompt_type, chunk_hash)

    if cached and isinstance(cached, dict) and "evaluations" in cached:
      logger.debug(f"Using cached evaluations for chunk={chunk.chunk_id}, prompt={prompt_type}")
      eval_items = []
      for item in cached["evaluations"]:
        if not isinstance(item, dict):
          continue
        eval_items.append(
            PromptEvaluationItem(
                speaker_id=item.get("speaker_id", "Unknown"),
                score=float(item.get("score", 0.0)),
                confidence=float(item.get("confidence", 0.0)),
                reason=str(item.get("reason", "No justification provided.")),
                supporting_quotes=item.get("supporting_quotes", []) if isinstance(item.get("supporting_quotes"), list) else []
            )
        )
      return PromptExecutionResult(
          prompt_type=prompt_type,
          meeting_id=chunk.meeting_id,
          chunk_id=chunk.chunk_id,
          evaluations=eval_items,
          model_version="cached",
          latency_ms=0.0,
          tokens_used=0,
          raw_response=cached
      )

    # Cache miss: execute Azure OpenAI completion
    try:
      system_inst, user_prompt = ConversationPrompts.get_prompt(prompt_type, chunk.formatted_text)
      raw_json, tokens = await self._client.complete_json(
          system_instruction=system_inst,
          user_prompt=user_prompt
      )

      eval_items = []
      eval_list = raw_json.get("evaluations", [])
      if isinstance(eval_list, list):
        for item in eval_list:
          if not isinstance(item, dict):
            continue
          eval_items.append(
              PromptEvaluationItem(
                  speaker_id=item.get("speaker_id", "Unknown"),
                  score=float(item.get("score", 0.0)),
                  confidence=float(item.get("confidence", 0.0)),
                  reason=str(item.get("reason", "No justification provided.")),
                  supporting_quotes=item.get("supporting_quotes", []) if isinstance(item.get("supporting_quotes"), list) else []
              )
          )

      # Save to cache
      await self._cache.save_cached_evaluation(chunk.meeting_id, prompt_type, chunk_hash, raw_json)

      return PromptExecutionResult(
          prompt_type=prompt_type,
          meeting_id=chunk.meeting_id,
          chunk_id=chunk.chunk_id,
          evaluations=eval_items,
          model_version=self._client._get_client()._azure_deployment if self._client._client else "gpt-5.5",
          latency_ms=0.0,
          tokens_used=tokens,
          raw_response=raw_json
      )
    except Exception as exc:
      logger.error(f"Failed prompt execution {prompt_type} on chunk {chunk.chunk_id}: {exc}")
      # Return empty result rather than aborting entire multi-prompt pass
      return PromptExecutionResult(
          prompt_type=prompt_type,
          meeting_id=chunk.meeting_id,
          chunk_id=chunk.chunk_id,
          evaluations=[],
          model_version="error",
          raw_response={"error": str(exc)}
      )

  @measure_latency("reasoning_engine.reason_over_chunks")
  async def reason_over_chunks(
      self,
      chunks: List[ConversationChunk],
      prompt_types: Optional[List[str]] = None
  ) -> List[PromptExecutionResult]:
    """Execute multiple independent reasoning prompts across all supplied chunks.

    Runs prompts concurrently across chunks using asyncio.gather.
    """
    if not chunks:
      return []

    target_prompts = prompt_types or list(ALL_EVIDENCE_TYPES)
    tasks = []

    for chunk in chunks:
      for p_type in target_prompts:
        tasks.append(self.execute_prompt_on_chunk(chunk, p_type))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_results = []
    for res in results:
      if isinstance(res, PromptExecutionResult):
        valid_results.append(res)
      elif isinstance(res, Exception):
        logger.error(f"Reasoning task raised unhandled exception: {res}", exc_info=res)

    logger.info(f"Reasoning over {len(chunks)} chunks completed: {len(valid_results)} prompt execution results generated.")
    return valid_results
