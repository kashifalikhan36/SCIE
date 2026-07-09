"""
Redis-backed caching for Azure OpenAI prompt evaluations.

Prevents duplicate or redundant GPT reasoning passes when transcript slices
have not changed, enabling fast and inexpensive incremental reasoning.
"""
import json
from typing import Dict, Any, Optional
from database.redis import get_redis
from engine.conversation.config import conversation_config
from engine.conversation.constants import REDIS_KEY_CONVERSATION_CACHE
from engine.conversation.logger import logger


class ConversationCache:
  """Async Redis cache for Conversation Reasoning Engine evaluations."""

  def __init__(self):
    self._ttl = conversation_config.CACHE_TTL_SEC

  def _build_key(self, meeting_id: str, prompt_type: str, chunk_hash: str) -> str:
    """Construct unique Redis cache key from prompt_type and deterministic SHA-256 chunk hash."""
    combined_hash = f"{prompt_type}_{chunk_hash}"
    return REDIS_KEY_CONVERSATION_CACHE.format(meeting_id=meeting_id, prompt_hash=combined_hash)

  async def get_cached_evaluation(
      self, meeting_id: str, prompt_type: str, chunk_hash: str
  ) -> Optional[Dict[str, Any]]:
    """Retrieve cached prompt evaluation dictionary from Redis if available."""
    try:
      redis = await get_redis()
      if redis is None:
        return None

      key = self._build_key(meeting_id, prompt_type, chunk_hash)
      raw = await redis.get(key)
      if raw:
        logger.debug(f"Cache hit for prompt {prompt_type} on chunk_hash={chunk_hash[:8]}")
        return json.loads(raw)
      return None
    except Exception as exc:
      logger.warning(f"ConversationCache: Failed to read from Redis: {exc}")
      return None

  async def save_cached_evaluation(
      self, meeting_id: str, prompt_type: str, chunk_hash: str, data: Dict[str, Any]
  ) -> None:
    """Store prompt evaluation dictionary into Redis cache with configured TTL."""
    try:
      redis = await get_redis()
      if redis is None:
        return

      key = self._build_key(meeting_id, prompt_type, chunk_hash)
      await redis.set(key, json.dumps(data), ex=self._ttl)
      logger.debug(f"Cached prompt {prompt_type} evaluation for chunk_hash={chunk_hash[:8]}")
    except Exception as exc:
      logger.warning(f"ConversationCache: Failed to save to Redis: {exc}")
