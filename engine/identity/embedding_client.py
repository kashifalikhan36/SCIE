"""
Azure OpenAI embedding client for the Identity Engine.

Responsibilities:
- Initialize the AsyncAzureOpenAI client once (singleton).
- Generate text embeddings using ``text-embedding-3-large``.
- Cache embeddings in Azure Cache for Redis to avoid duplicate API calls.
- Support async requests with configurable timeout and retry.
- Gracefully degrade (return None) when Azure OpenAI is unavailable.
"""
import asyncio
import json
import logging
from typing import List, Optional

from openai import AsyncAzureOpenAI

from database.redis import get_redis
from engine.identity.config import identity_config
from engine.identity.constants import REDIS_KEY_EMBEDDING_CACHE
from engine.identity.utils import hash_text
from engine.identity.exceptions import EmbeddingClientError, EmbeddingTimeoutError

logger = logging.getLogger("SCIE.identity_engine.embedding_client")


class EmbeddingClient:
  """Async Azure OpenAI embedding client with Redis caching.

  Usage::

      client = EmbeddingClient.get_instance()
      embedding = await client.embed("John Smith")

  Features:
  - Singleton: client initialized once per process.
  - Async: non-blocking requests via ``AsyncAzureOpenAI``.
  - Redis caching: SHA-256 hash of input text → cached JSON vector.
  - Retry: up to ``EMBEDDING_RETRY_COUNT`` attempts with exponential backoff.
  - Graceful degradation: returns ``None`` on any failure; pipeline continues.
  """

  _instance: Optional["EmbeddingClient"] = None
  _client: Optional[AsyncAzureOpenAI] = None

  @classmethod
  def get_instance(cls) -> "EmbeddingClient":
    """Returns the process-wide singleton instance."""
    if cls._instance is None:
      cls._instance = cls()
    return cls._instance

  def _get_client(self) -> Optional[AsyncAzureOpenAI]:
    """Lazy-initializes the AsyncAzureOpenAI client."""
    if self._client is not None:
      return self._client

    api_key = identity_config.AZURE_OPENAI_API_KEY
    endpoint = identity_config.AZURE_OPENAI_ENDPOINT
    api_version = identity_config.AZURE_OPENAI_API_VERSION

    if not api_key or not endpoint:
      logger.warning(
          "EmbeddingClient: AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT not configured. "
          "Semantic matching will be unavailable."
      )
      return None

    try:
      self._client = AsyncAzureOpenAI(
          api_key=api_key,
          azure_endpoint=endpoint,
          api_version=api_version,
      )
      logger.info(
          f"EmbeddingClient: Initialized AsyncAzureOpenAI for endpoint={endpoint}, "
          f"deployment={identity_config.EMBEDDING_DEPLOYMENT}"
      )
      return self._client
    except Exception as exc:
      logger.error(f"EmbeddingClient: Failed to initialize Azure OpenAI client: {exc}")
      return None

  async def embed(self, text: str) -> Optional[List[float]]:
    """Generates a text embedding vector, checking the Redis cache first.

    Args:
        text: Input text to embed (e.g. a candidate name).

    Returns:
        List of float values (the embedding vector), or ``None`` if the
        request fails after all retries or Azure OpenAI is unavailable.
    """
    if not text or not text.strip():
      return None

    text = text.strip()

    # ── 1. Redis cache lookup ─────────────────────────────────────────────
    cached = await self._cache_get(text)
    if cached is not None:
      logger.debug(f"EmbeddingClient: Cache hit for '{text[:60]}'")
      return cached

    # ── 2. Azure OpenAI request with retry ───────────────────────────────
    client = self._get_client()
    if client is None:
      logger.warning("EmbeddingClient: Azure OpenAI unavailable — skipping embedding.")
      return None

    for attempt in range(identity_config.EMBEDDING_RETRY_COUNT):
      try:
        response = await asyncio.wait_for(
            client.embeddings.create(
                input=[text],
                model=identity_config.EMBEDDING_DEPLOYMENT,
            ),
            timeout=identity_config.EMBEDDING_TIMEOUT_SEC,
        )
        embedding = response.data[0].embedding
        logger.debug(
            f"EmbeddingClient: Generated embedding for '{text[:60]}' "
            f"(dim={len(embedding)}, attempt={attempt + 1})"
        )

        # ── 3. Store in Redis cache ───────────────────────────────────────
        await self._cache_set(text, embedding)
        return embedding

      except asyncio.TimeoutError:
        delay = identity_config.EMBEDDING_RETRY_DELAY_SEC * (2 ** attempt)
        logger.warning(
            f"EmbeddingClient: Timeout on attempt {attempt + 1} for '{text[:60]}'. "
            f"Retrying in {delay:.1f}s..."
        )
        if attempt < identity_config.EMBEDDING_RETRY_COUNT - 1:
          await asyncio.sleep(delay)

      except Exception as exc:
        delay = identity_config.EMBEDDING_RETRY_DELAY_SEC * (2 ** attempt)
        logger.error(
            f"EmbeddingClient: API error on attempt {attempt + 1}: {exc}. "
            f"Retrying in {delay:.1f}s..."
        )
        if attempt < identity_config.EMBEDDING_RETRY_COUNT - 1:
          await asyncio.sleep(delay)

    logger.error(
        f"EmbeddingClient: All {identity_config.EMBEDDING_RETRY_COUNT} attempts failed "
        f"for text '{text[:60]}'. Returning None."
    )
    return None

  async def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
    """Generates embeddings for multiple texts concurrently.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (same length as ``texts``).
        Items are ``None`` for any texts that failed.
    """
    tasks = [self.embed(t) for t in texts]
    return list(await asyncio.gather(*tasks))

  async def _cache_get(self, text: str) -> Optional[List[float]]:
    """Retrieves a cached embedding from Redis.

    Returns:
        The embedding vector if cached, otherwise ``None``.
    """
    try:
      redis = await get_redis()
      if redis is None:
        return None
      key = REDIS_KEY_EMBEDDING_CACHE.format(text_hash=hash_text(text))
      raw = await redis.get(key)
      if raw is None:
        return None
      return json.loads(raw)
    except Exception as exc:
      logger.debug(f"EmbeddingClient: Cache read error: {exc}")
      return None

  async def _cache_set(self, text: str, embedding: List[float]) -> None:
    """Stores an embedding in Redis with the configured TTL.

    Args:
        text: The original input text (used to derive the cache key).
        embedding: The embedding vector to cache.
    """
    try:
      redis = await get_redis()
      if redis is None:
        return
      key = REDIS_KEY_EMBEDDING_CACHE.format(text_hash=hash_text(text))
      await redis.set(
          key,
          json.dumps(embedding),
          ex=identity_config.EMBEDDING_CACHE_TTL_SEC
      )
      logger.debug(f"EmbeddingClient: Cached embedding for '{text[:60]}'")
    except Exception as exc:
      logger.debug(f"EmbeddingClient: Cache write error (non-critical): {exc}")
