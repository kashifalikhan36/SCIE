"""
Evidence Availability & Validation Module for the Dynamic Weighting Engine.

Determines whether each evidence source is AVAILABLE, UNAVAILABLE, DEGRADED, INVALID,
or UNKNOWN. Unavailable or invalid evidence receives zero contribution weight.

(`engine/weighting/evidence_validator.py`)
"""
from typing import Dict, Any, Optional
from engine.weighting.constants import (
    EvidenceAvailability,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA,
    ALL_DOMAINS
)
from engine.weighting.config import weighting_config
from engine.weighting.schemas import UpstreamParticipantState, EvidencePayloads
from engine.weighting.utils import now_ms


class EvidenceValidator:
  """Validates availability status and basic integrity across all 7 evidence domains."""

  def evaluate_availability(
      self,
      payloads: EvidencePayloads,
      p_state: UpstreamParticipantState
  ) -> Dict[str, EvidenceAvailability]:
    """Evaluate all 7 domains and map to explicit EvidenceAvailability enum."""
    results: Dict[str, EvidenceAvailability] = {}

    results[DOMAIN_VISUAL] = self._check_visual(payloads.visual_evidence, p_state)
    results[DOMAIN_VOICE] = self._check_voice(payloads.voice_evidence, p_state)
    results[DOMAIN_TRANSCRIPT] = self._check_transcript(payloads.transcript_evidence, p_state)
    results[DOMAIN_CONVERSATION] = self._check_conversation(payloads.conversation_evidence, p_state)
    results[DOMAIN_BEHAVIOR] = self._check_behavior(payloads.behavior_evidence, p_state)
    results[DOMAIN_IDENTITY] = self._check_identity(payloads.identity_evidence, p_state)
    results[DOMAIN_METADATA] = self._check_metadata(payloads.metadata_evidence, p_state)

    return results

  def _check_visual(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not p_state.camera_on or not p_state.face_visible:
      return EvidenceAvailability.UNAVAILABLE
    if not ev:
      return EvidenceAvailability.UNAVAILABLE
    status_str = str(ev.get("status", "")).upper()
    if status_str in ("UNAVAILABLE", "OFF", "FAILED"):
      return EvidenceAvailability.UNAVAILABLE
    if status_str == "DEGRADED":
      return EvidenceAvailability.DEGRADED
    conf = float(ev.get("confidence", ev.get("score", 1.0)) or 0.0)
    if conf < weighting_config.MIN_VISUAL_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_voice(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not p_state.mic_on or not p_state.voice_detected:
      return EvidenceAvailability.UNAVAILABLE
    if not ev:
      return EvidenceAvailability.UNAVAILABLE
    status_str = str(ev.get("status", "")).upper()
    if status_str in ("UNAVAILABLE", "MUTED", "FAILED"):
      return EvidenceAvailability.UNAVAILABLE
    if status_str == "DEGRADED":
      return EvidenceAvailability.DEGRADED
    conf = float(ev.get("confidence", ev.get("score", 1.0)) or 0.0)
    if conf < weighting_config.MIN_VOICE_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_transcript(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not p_state.transcript_available:
      return EvidenceAvailability.UNAVAILABLE
    if not ev:
      return EvidenceAvailability.UNAVAILABLE
    status_str = str(ev.get("status", "")).upper()
    if status_str in ("UNAVAILABLE", "FAILED"):
      return EvidenceAvailability.UNAVAILABLE
    conf = float(ev.get("confidence", ev.get("reliability", 1.0)) or 0.0)
    if conf < weighting_config.MIN_TRANSCRIPT_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_conversation(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not p_state.transcript_available:
      return EvidenceAvailability.UNAVAILABLE
    if not ev:
      return EvidenceAvailability.UNAVAILABLE
    status_str = str(ev.get("status", "")).upper()
    if status_str in ("UNAVAILABLE", "FAILED"):
      return EvidenceAvailability.UNAVAILABLE
    conf = float(ev.get("confidence", ev.get("reliability", 1.0)) or 0.0)
    if conf < weighting_config.MIN_CONVERSATION_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_behavior(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not ev:
      return EvidenceAvailability.AVAILABLE  # Default behavior features can still be inferred from state
    conf = float(ev.get("confidence", ev.get("reliability", 1.0)) or 0.0)
    if conf < weighting_config.MIN_BEHAVIOR_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_identity(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not ev:
      return EvidenceAvailability.AVAILABLE  # Identity can fall back to metadata
    conf = float(ev.get("confidence", ev.get("reliability", 1.0)) or 0.0)
    if conf < weighting_config.MIN_IDENTITY_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE

  def _check_metadata(
      self,
      ev: Optional[Dict[str, Any]],
      p_state: UpstreamParticipantState
  ) -> EvidenceAvailability:
    if not ev:
      return EvidenceAvailability.AVAILABLE  # Basic participant ID metadata is always present
    conf = float(ev.get("confidence", ev.get("reliability", 1.0)) or 0.0)
    if conf < weighting_config.MIN_METADATA_CONFIDENCE:
      return EvidenceAvailability.DEGRADED
    return EvidenceAvailability.AVAILABLE
