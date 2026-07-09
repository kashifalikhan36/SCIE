from pydantic_settings import BaseSettings, SettingsConfigDict


class BehaviorEngineSettings(BaseSettings):
  """
  Behavior Engine configuration settings.

  All values can be overridden via environment variables prefixed with
  ``BEHAVIOR_`` (e.g. ``BEHAVIOR_WORKER_COUNT=4``).

  This engine produces behavioral features and evidence only.
  It does NOT perform candidate identification or GPT reasoning.
  """

  # ── Thresholds ─────────────────────────────────────────────────────────────
  MIN_SPEAKING_DURATION_SEC: float = 1.0
  MIN_INTERRUPTION_DURATION_SEC: float = 0.5
  CAMERA_VISIBILITY_THRESHOLD: float = 0.50
  FAST_RESPONSE_THRESHOLD_SEC: float = 3.0
  SLOW_RESPONSE_THRESHOLD_SEC: float = 15.0
  SPEECH_PAUSE_MERGE_SEC: float = 0.75

  # ── Engagement Score Weights (must sum to 1.0) ─────────────────────────────
  WEIGHT_SPEAKING: float = 0.35
  WEIGHT_CAMERA: float = 0.25
  WEIGHT_TRANSCRIPT: float = 0.20
  WEIGHT_RESPONSE: float = 0.10
  WEIGHT_SCREEN: float = 0.10

  # ── Engagement Cutoffs ─────────────────────────────────────────────────────
  ENGAGEMENT_HIGH_THRESHOLD: float = 0.75
  ENGAGEMENT_MEDIUM_THRESHOLD: float = 0.45

  # ── Update Intervals ───────────────────────────────────────────────────────
  INTERVAL_ENGAGEMENT_SEC: float = 5.0
  INTERVAL_SUMMARY_SEC: float = 10.0

  # ── Redis State Expiration ─────────────────────────────────────────────────
  # TTL for live behavior state in Azure Cache for Redis (2 hours)
  REDIS_STATE_TTL_SEC: int = 7200

  # ── Worker Pool ────────────────────────────────────────────────────────────
  WORKER_COUNT: int = 2
  WORKER_QUEUE_MAXSIZE: int = 300
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 0.5

  # ── History ────────────────────────────────────────────────────────────────
  TIMELINE_MAX_LENGTH: int = 500

  model_config = SettingsConfigDict(env_prefix="BEHAVIOR_")


behavior_config = BehaviorEngineSettings()
