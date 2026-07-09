"""
Configuration settings for the Evidence Fusion Engine (`engine/fusion/`).

All values can be overridden via environment variables prefixed with `FUSION_`
(e.g., `FUSION_MINIMUM_CONFIDENCE=0.15`).

Configures thresholds, weight decay, freshness expiration, worker limits, and default domain weights.
"""
from typing import Dict
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from engine.fusion.constants import (
    DOMAIN_IDENTITY, DOMAIN_VISUAL, DOMAIN_VOICE,
    DOMAIN_BEHAVIOR, DOMAIN_CONVERSATION, DOMAIN_TRANSCRIPT
)


class FusionEngineSettings(BaseSettings):
  """Evidence Fusion Engine configuration settings."""

  # ── Confidence & Multi-Signal Requirements ──────────────────────────────────
  MINIMUM_CONFIDENCE: float = Field(default=0.10, ge=0.0, le=1.0)
  MINIMUM_EVIDENCE_COUNT: int = Field(default=2, ge=1)
  RANKING_THRESHOLD: float = Field(default=0.50, ge=0.0, le=1.0)

  # ── Freshness & Decay ───────────────────────────────────────────────────────
  # Signals older than this start decaying exponentially
  FRESHNESS_TIMEOUT_SEC: float = Field(default=30.0, ge=0.0)
  # Signals older than this are marked STALE
  MAX_STALE_DURATION_SEC: float = Field(default=300.0, ge=0.0)
  # Decay rate per second after FRESHNESS_TIMEOUT_SEC
  WEIGHT_DECAY_RATE: float = Field(default=0.05, ge=0.0, le=1.0)

  # ── Default Base Weights (must sum to ~1.0) ─────────────────────────────────
  DEFAULT_WEIGHTS: Dict[str, float] = Field(
      default={
          DOMAIN_IDENTITY: 0.25,
          DOMAIN_VISUAL: 0.25,
          DOMAIN_VOICE: 0.20,
          DOMAIN_BEHAVIOR: 0.15,
          DOMAIN_CONVERSATION: 0.15,
      }
  )

  # ── Worker & Queue Parameters ───────────────────────────────────────────────
  WORKER_COUNT: int = Field(default=4, ge=1)
  WORKER_QUEUE_MAXSIZE: int = Field(default=1000, ge=10)
  WORKER_RETRY_COUNT: int = Field(default=3, ge=1)
  WORKER_RETRY_DELAY_SEC: float = Field(default=1.0, ge=0.1)

  # ── Storage & Caching TTLs ──────────────────────────────────────────────────
  REDIS_STATE_TTL_SEC: int = Field(default=7200, ge=60)
  HISTORY_MAX_LENGTH: int = Field(default=100, ge=10)
  DEDUPLICATION_WINDOW_SEC: float = Field(default=2.0, ge=0.0)

  model_config = SettingsConfigDict(env_prefix="FUSION_", extra="ignore")


fusion_config = FusionEngineSettings()
