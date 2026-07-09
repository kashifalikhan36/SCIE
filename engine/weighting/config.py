"""
Pydantic V2 BaseSettings configuration for the SCIE Dynamic Weighting Engine.

All values can be overridden via environment variables prefixed with ``WEIGHTING_``
(e.g., ``WEIGHTING_MIN_FACE_QUALITY=0.45``).

(`engine/weighting/config.py`)
"""
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from engine.weighting.constants import (
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA,
    WeightingStrategyType
)


class WeightingEngineSettings(BaseSettings):
  """
  Dynamic Weighting Engine configuration settings.

  This engine only calculates optimal contribution weights (`DynamicWeightProfile`).
  It does NOT perform candidate identification or GPT reasoning.
  """

  # ── Minimum Confidence Thresholds ──────────────────────────────────────────
  MIN_VISUAL_CONFIDENCE: float = 0.20
  MIN_VOICE_CONFIDENCE: float = 0.20
  MIN_TRANSCRIPT_CONFIDENCE: float = 0.25
  MIN_CONVERSATION_CONFIDENCE: float = 0.25
  MIN_BEHAVIOR_CONFIDENCE: float = 0.20
  MIN_IDENTITY_CONFIDENCE: float = 0.20
  MIN_METADATA_CONFIDENCE: float = 0.15

  # ── Minimum Quality & Duration Cutoffs ─────────────────────────────────────
  MIN_FACE_QUALITY: float = 0.35
  MIN_FACE_SIZE_RATIO: float = 0.05
  MIN_SPEECH_DURATION_SEC: float = 0.5
  MIN_SPEECH_DIARIZATION_CONFIDENCE: float = 0.40
  MIN_WHISPER_CONFIDENCE: float = 0.40
  MIN_TRANSCRIPT_COVERAGE_RATIO: float = 0.30

  # ── Freshness & Staleness Boundaries (Seconds) ─────────────────────────────
  FRESHNESS_TIMEOUT_SEC: float = 30.0
  MAX_STALE_DURATION_SEC: float = 120.0
  STALENESS_HALF_LIFE_SEC: float = 60.0

  # ── Meeting Context Thresholds ─────────────────────────────────────────────
  LONG_MEETING_DURATION_SEC: float = 900.0  # 15 minutes
  QUALITY_CHANGE_RECOMPUTE_DELTA: float = 0.05

  # ── Base Strategy Weights (must sum to 1.0 per strategy) ───────────────────
  DEFAULT_STRATEGY_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.22,
      DOMAIN_VOICE: 0.18,
      DOMAIN_TRANSCRIPT: 0.15,
      DOMAIN_CONVERSATION: 0.18,
      DOMAIN_BEHAVIOR: 0.12,
      DOMAIN_IDENTITY: 0.10,
      DOMAIN_METADATA: 0.05,
  }

  INTERVIEW_STARTED_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.20,
      DOMAIN_VOICE: 0.15,
      DOMAIN_TRANSCRIPT: 0.10,
      DOMAIN_CONVERSATION: 0.15,
      DOMAIN_BEHAVIOR: 0.10,
      DOMAIN_IDENTITY: 0.20,
      DOMAIN_METADATA: 0.10,
  }

  INTERVIEW_IN_PROGRESS_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.20,
      DOMAIN_VOICE: 0.20,
      DOMAIN_TRANSCRIPT: 0.18,
      DOMAIN_CONVERSATION: 0.22,
      DOMAIN_BEHAVIOR: 0.10,
      DOMAIN_IDENTITY: 0.07,
      DOMAIN_METADATA: 0.03,
  }

  CODING_ROUND_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.15,
      DOMAIN_VOICE: 0.20,
      DOMAIN_TRANSCRIPT: 0.20,
      DOMAIN_CONVERSATION: 0.25,
      DOMAIN_BEHAVIOR: 0.15,
      DOMAIN_IDENTITY: 0.03,
      DOMAIN_METADATA: 0.02,
  }

  BEHAVIOR_ROUND_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.25,
      DOMAIN_VOICE: 0.20,
      DOMAIN_TRANSCRIPT: 0.15,
      DOMAIN_CONVERSATION: 0.20,
      DOMAIN_BEHAVIOR: 0.15,
      DOMAIN_IDENTITY: 0.03,
      DOMAIN_METADATA: 0.02,
  }

  CAMERA_OFF_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.00,
      DOMAIN_VOICE: 0.28,
      DOMAIN_TRANSCRIPT: 0.22,
      DOMAIN_CONVERSATION: 0.26,
      DOMAIN_BEHAVIOR: 0.14,
      DOMAIN_IDENTITY: 0.07,
      DOMAIN_METADATA: 0.03,
  }

  VOICE_ONLY_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.00,
      DOMAIN_VOICE: 0.35,
      DOMAIN_TRANSCRIPT: 0.25,
      DOMAIN_CONVERSATION: 0.25,
      DOMAIN_BEHAVIOR: 0.05,
      DOMAIN_IDENTITY: 0.07,
      DOMAIN_METADATA: 0.03,
  }

  VIDEO_ONLY_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.45,
      DOMAIN_VOICE: 0.00,
      DOMAIN_TRANSCRIPT: 0.00,
      DOMAIN_CONVERSATION: 0.00,
      DOMAIN_BEHAVIOR: 0.35,
      DOMAIN_IDENTITY: 0.15,
      DOMAIN_METADATA: 0.05,
  }

  METADATA_ONLY_WEIGHTS: Dict[str, float] = {
      DOMAIN_VISUAL: 0.00,
      DOMAIN_VOICE: 0.00,
      DOMAIN_TRANSCRIPT: 0.00,
      DOMAIN_CONVERSATION: 0.00,
      DOMAIN_BEHAVIOR: 0.00,
      DOMAIN_IDENTITY: 0.60,
      DOMAIN_METADATA: 0.40,
  }

  # ── Storage & Expiration ───────────────────────────────────────────────────
  REDIS_STATE_TTL_SEC: int = 7200
  HISTORY_MAX_LENGTH: int = 500

  # ── Worker Pool ────────────────────────────────────────────────────────────
  WORKER_COUNT: int = 2
  WORKER_QUEUE_MAXSIZE: int = 300
  WORKER_RETRY_COUNT: int = 3
  WORKER_RETRY_DELAY_SEC: float = 0.5

  model_config = SettingsConfigDict(env_prefix="WEIGHTING_")


weighting_config = WeightingEngineSettings()
