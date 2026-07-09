from pydantic_settings import BaseSettings, SettingsConfigDict


class TranscriptEngineSettings(BaseSettings):
  """
  Transcript Engine configuration settings.

  All values can be overridden via environment variables prefixed with
  ``TRANSCRIPT_`` (e.g. ``TRANSCRIPT_WORKER_COUNT=4``).
  """

  # ── Buffer ────────────────────────────────────────────────────────────────
  # Maximum number of chunks kept in the per-meeting streaming buffer.
  # Older chunks are evicted once this limit is reached.
  BUFFER_MAX_SIZE: int = 200

  # Maximum tolerated time-gap (in ms) between two consecutive buffer chunks
  # before they are considered non-overlapping / out-of-order.
  MERGE_TIMEOUT_MS: int = 1500

  # ── Partial transcript ────────────────────────────────────────────────────
  # Number of seconds after which a Redis partial key automatically expires.
  # Prevents stale partials from disconnected speakers persisting indefinitely.
  REDIS_PARTIAL_TTL_SEC: int = 120

  # Maximum age (seconds) a partial is kept before being force-cleared.
  MAX_PARTIAL_LIFETIME_SEC: int = 30

  # ── Redis live state ──────────────────────────────────────────────────────
  # TTL for the ParticipantTranscriptState blob. Keeps state alive for the
  # duration of a long meeting and cleans itself up automatically after.
  REDIS_STATE_TTL_SEC: int = 7200   # 2 hours

  # Maximum number of utterances kept in the per-speaker Redis history list.
  HISTORY_MAX_SIZE: int = 200

  # ── Duplicate-finalization guard ──────────────────────────────────────────
  # Time window (ms) used to consider two final events with the same speaker
  # and start_time as identical.  Prevents double-archiving.
  FINALIZE_DEDUP_WINDOW_MS: int = 500

  # ── Quality filter ────────────────────────────────────────────────────────
  # Transcript chunks below this confidence score are silently discarded.
  MIN_CONFIDENCE_THRESHOLD: float = 0.0

  # ── Conversation turn grouping ────────────────────────────────────────────
  # Maximum silence gap (seconds) between consecutive utterances from the same
  # speaker that still qualify as a single conversational turn.
  CONVERSATION_TURN_GAP_SEC: float = 5.0

  # ── Background workers ────────────────────────────────────────────────────
  WORKER_QUEUE_MAXSIZE: int = 200
  WORKER_COUNT: int = 2
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 0.5

  model_config = SettingsConfigDict(
      env_prefix="TRANSCRIPT_",
      case_sensitive=True,
      env_file=".env",
      extra="ignore"
  )


transcript_config = TranscriptEngineSettings()
