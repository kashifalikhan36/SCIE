"""
Configuration and Settings Module for the SCIE Confidence Engine (`engine/confidence/`).

Utilizes Pydantic V2 BaseSettings loaded from environment variables prefixed with `CONFIDENCE_`.
Ensures zero hardcoded magic numbers across weights, decay rates, recovery bounds, and timeline resolution.
(`engine/confidence/config.py`)
"""
from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from engine.confidence.constants import (
    EvidenceSource, NormalizationStrategyType, CalculationStrategyType
)


class ConfidenceEngineSettings(BaseSettings):
  """Central configuration settings for the production Confidence Engine."""
  model_config = SettingsConfigDict(
      env_prefix="CONFIDENCE_",
      env_file=".env",
      env_file_encoding="utf-8",
      extra="ignore"
  )

  # Core execution configuration
  DEFAULT_NORMALIZATION_STRATEGY: str = Field(default=NormalizationStrategyType.LINEAR.value)
  DEFAULT_CALCULATION_STRATEGY: str = Field(default=CalculationStrategyType.WEIGHTED_AVERAGE.value)
  WORKER_COUNT: int = Field(default=4, description="Background async worker pool count")
  WORKER_QUEUE_MAXSIZE: int = Field(default=500, description="Max job capacity in worker queue")
  WORKER_RETRY_COUNT: int = Field(default=3, description="Max retries for transient processing failures")

  # Default Domain Weights (Initial baseline before dynamic scaling)
  DEFAULT_WEIGHTS: Dict[str, float] = Field(
      default={
          EvidenceSource.IDENTITY.value: 0.20,
          EvidenceSource.FACE.value: 0.18,
          EvidenceSource.VOICE.value: 0.18,
          EvidenceSource.CONVERSATION.value: 0.18,
          EvidenceSource.BEHAVIOR.value: 0.14,
          EvidenceSource.TRANSCRIPT.value: 0.12,
          EvidenceSource.EMOTION.value: 0.0,  # Reserved for future integration
          EvidenceSource.GAZE.value: 0.0,     # Reserved for future integration
      },
      description="Configurable base weights across all recognized evidence sources"
  )

  # Confidence Bounds & Thresholds
  MIN_EVIDENCE_CONFIDENCE_GATE: float = Field(default=0.25, description="Minimum evidence confidence required to contribute positive weight")
  MIN_ACTIVE_SOURCES_FOR_HIGH_CONFIDENCE: int = Field(default=3, description="Min active sources required to exceed 0.85 confidence")
  SINGLE_SOURCE_CONFIDENCE_CAP: float = Field(default=0.45, description="Maximum confidence ceiling when only one evidence source is active")

  # Dynamic Weighting & Staleness Timers
  EVIDENCE_STALE_TIMEOUT_SEC: float = Field(default=30.0, description="Duration in seconds before an unupdated source is marked stale and begins decay")
  EVIDENCE_MISSING_TIMEOUT_SEC: float = Field(default=120.0, description="Duration after which an unupdated source is treated as completely missing (weight -> 0)")

  # Continuous Decay & Recovery Rates
  CONFIDENCE_DECAY_RATE_PER_STEP: float = Field(default=0.05, description="Fractional decay rate applied when evidence sources disappear or become stale")
  CONFIDENCE_RECOVERY_RATE_PER_STEP: float = Field(default=0.15, description="Smoothing interpolation rate when lost signals recover")
  MAX_DECAY_PER_STEP: float = Field(default=0.10, description="Maximum downward drop allowed in a single calculation turn")
  MAX_RECOVERY_PER_STEP: float = Field(default=0.20, description="Maximum upward jump allowed in a single calculation turn when signals recover")

  # Timeline & Storage Configuration
  TIMELINE_RESOLUTION_SEC: float = Field(default=30.0, description="Minimum seconds between dedicated timeline history snapshots")
  MAX_TIMELINE_HISTORY_ITEMS: int = Field(default=500, description="Max history snapshots kept in rolling memory state before trimming")
  REDIS_STATE_TTL_SEC: int = Field(default=7200, description="TTL in seconds for live participant state in Azure Cache for Redis")


# Singleton instance loaded on start
confidence_config = ConfidenceEngineSettings()
