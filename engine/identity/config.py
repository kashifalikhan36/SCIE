from pydantic_settings import BaseSettings, SettingsConfigDict


class IdentityEngineSettings(BaseSettings):
  """
  Identity Engine configuration settings.

  All values can be overridden via environment variables prefixed with
  ``IDENTITY_`` (e.g. ``IDENTITY_WORKER_COUNT=4``).

  This engine produces IdentityEvidence only.
  It does NOT make candidate decisions.
  """

  # ── Azure OpenAI Embedding ─────────────────────────────────────────────────
  AZURE_OPENAI_API_KEY: str = ""
  AZURE_OPENAI_ENDPOINT: str = ""
  AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
  EMBEDDING_DEPLOYMENT: str = "text-embedding-3-large"
  EMBEDDING_TIMEOUT_SEC: float = 10.0
  EMBEDDING_RETRY_COUNT: int = 3
  EMBEDDING_RETRY_DELAY_SEC: float = 0.5
  EMBEDDING_DIMENSIONS: int = 3072   # text-embedding-3-large native dimension

  # ── Similarity Thresholds ──────────────────────────────────────────────────
  # Minimum RapidFuzz score to include in evidence (0.0 = always include)
  MIN_FUZZY_SCORE: float = 0.40
  # Minimum semantic cosine similarity to treat as supporting evidence
  MIN_SEMANTIC_SCORE: float = 0.50
  # Minimum email score to treat as a meaningful signal
  MIN_EMAIL_SCORE: float = 0.30

  # ── Email Matching Scores ──────────────────────────────────────────────────
  EMAIL_EXACT_SCORE: float = 1.0
  EMAIL_USERNAME_MATCH_SCORE: float = 0.90
  EMAIL_DOMAIN_ONLY_SCORE: float = 0.30

  # ── Confidence Weights (must sum to 1.0) ──────────────────────────────────
  # Each weight is applied proportionally; active signals are normalized.
  WEIGHT_EMAIL: float = 0.30
  WEIGHT_SEMANTIC: float = 0.25
  WEIGHT_FUZZY: float = 0.20
  WEIGHT_ALIAS: float = 0.15
  WEIGHT_METADATA: float = 0.10

  # ── Embedding Cache ────────────────────────────────────────────────────────
  # Redis TTL for cached embeddings (24 hours)
  EMBEDDING_CACHE_TTL_SEC: int = 86400

  # ── Redis State Expiration ─────────────────────────────────────────────────
  # TTL for live identity state in Azure Cache for Redis (2 hours)
  REDIS_STATE_TTL_SEC: int = 7200

  # ── Worker Pool ────────────────────────────────────────────────────────────
  WORKER_COUNT: int = 2
  WORKER_QUEUE_MAXSIZE: int = 200
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 0.5

  # ── History ────────────────────────────────────────────────────────────────
  HISTORY_MAX_LENGTH: int = 100

  model_config = SettingsConfigDict(
      env_prefix="IDENTITY_",
      case_sensitive=True,
      env_file=".env",
      extra="ignore"
  )


identity_config = IdentityEngineSettings()
