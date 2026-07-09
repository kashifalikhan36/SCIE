from pydantic_settings import BaseSettings, SettingsConfigDict


class ConversationEngineSettings(BaseSettings):
  """
  Conversation Reasoning Engine configuration settings.

  All values can be overridden via environment variables prefixed with
  ``CONVERSATION_`` (e.g. ``CONVERSATION_TEMPERATURE=0.2``), or general
  Azure OpenAI variables where applicable.

  This engine reasons over the conversation structure.
  It does NOT decide the candidate or perform evidence fusion.
  """

  # ── Azure OpenAI Foundry Settings ──────────────────────────────────────────
  AZURE_OPENAI_API_KEY: str = ""
  AZURE_OPENAI_ENDPOINT: str = ""
  AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
  CONVERSATION_DEPLOYMENT_NAME: str = "gpt-5.5"

  # ── Model & Request Parameters ─────────────────────────────────────────────
  TEMPERATURE: float = 0.1
  MAX_TOKENS: int = 2000
  TIMEOUT_SEC: float = 30.0
  RETRY_COUNT: int = 3
  RETRY_DELAY_SEC: float = 1.0

  # ── Chunking & Analysis Boundaries ─────────────────────────────────────────
  # Chunk size by number of conversation turns
  CHUNK_SIZE_TURNS: int = 15
  # Or by maximum duration in seconds per chunk (5 minutes)
  CHUNK_SIZE_SECONDS: float = 300.0

  # ── Caching & State Expiration ─────────────────────────────────────────────
  # TTL for cached GPT prompt evaluations (24 hours)
  CACHE_TTL_SEC: int = 86400
  # TTL for live conversation state in Azure Cache for Redis (2 hours)
  REDIS_STATE_TTL_SEC: int = 7200

  # ── Worker Pool ────────────────────────────────────────────────────────────
  WORKER_COUNT: int = 2
  WORKER_QUEUE_MAXSIZE: int = 200

  model_config = SettingsConfigDict(env_prefix="CONVERSATION_")


conversation_config = ConversationEngineSettings()
