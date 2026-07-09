from pydantic_settings import BaseSettings, SettingsConfigDict


class AssociationEngineSettings(BaseSettings):
  """
  Participant Identity Resolution Engine configuration settings.

  All values can be overridden via environment variables prefixed with
  ``ASSOCIATION_`` (e.g. ``ASSOCIATION_WORKER_COUNT=4``).
  """

  # ── Thresholds ────────────────────────────────────────────────────────────
  MIN_METADATA_SIMILARITY: float = 0.60
  MIN_TRANSCRIPT_CONFIDENCE: float = 0.65
  ASSOCIATION_CONFIDENCE_THRESHOLD: float = 0.70

  # ── Timeouts & Intervals ──────────────────────────────────────────────────
  # Maximum time window (seconds) to consider multi-modal events as co-occurring
  TIMELINE_COOCCURRENCE_WINDOW_SEC: float = 5.0
  # Time after which an inactive participant association is considered stale
  ASSOCIATION_TIMEOUT_SEC: int = 300
  # Interval for periodic re-evaluation / re-association checks
  REASSOCIATION_INTERVAL_SEC: float = 30.0

  # ── History ───────────────────────────────────────────────────────────────
  # Maximum length of identity history list stored in Redis per participant
  HISTORY_MAX_LENGTH: int = 100

  # ── Confidence Weights ────────────────────────────────────────────────────
  # Configurable weighting strategy for combining evidences into final confidence.
  WEIGHT_METADATA: float = 0.25
  WEIGHT_TIMELINE: float = 0.25
  WEIGHT_SPEAKER: float = 0.20
  WEIGHT_TRANSCRIPT: float = 0.15
  WEIGHT_TRACK: float = 0.15

  # ── Worker Pool Configuration ─────────────────────────────────────────────
  WORKER_QUEUE_MAXSIZE: int = 200
  WORKER_COUNT: int = 2
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 0.5

  # ── Redis State Expiration ────────────────────────────────────────────────
  # TTL for cached live participant state in Azure Cache for Redis (2 hours)
  REDIS_STATE_TTL_SEC: int = 7200

  model_config = SettingsConfigDict(
      env_prefix="ASSOCIATION_",
      case_sensitive=True,
      env_file=".env",
      extra="ignore"
  )


association_config = AssociationEngineSettings()
