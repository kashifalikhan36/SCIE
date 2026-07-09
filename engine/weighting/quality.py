"""
Quality Evaluation Module for the Dynamic Weighting Engine.

Evaluates multi-faceted quality across all 7 domains and returns normalized
scores between 0.0 and 1.0.

(`engine/weighting/quality.py`)
"""
from typing import Dict, Any, Optional
from engine.weighting.constants import (
    EvidenceAvailability,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
from engine.weighting.config import weighting_config
from engine.weighting.schemas import UpstreamParticipantState, EvidencePayloads, QualityScores
from engine.weighting.utils import clamp


class QualityEvaluator:
  """Evaluates granular domain signal quality to guide dynamic weight adjustments."""

  def evaluate_quality(
      self,
      payloads: EvidencePayloads,
      availabilities: Dict[str, EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> QualityScores:
    """Compute normalized [0.0, 1.0] quality score per domain."""
    vq = self._eval_visual_quality(payloads.visual_evidence, availabilities.get(DOMAIN_VISUAL), p_state)
    aq = self._eval_voice_quality(payloads.voice_evidence, availabilities.get(DOMAIN_VOICE), p_state)
    tq = self._eval_transcript_quality(payloads.transcript_evidence, availabilities.get(DOMAIN_TRANSCRIPT), p_state)
    cq = self._eval_conversation_quality(payloads.conversation_evidence, availabilities.get(DOMAIN_CONVERSATION), p_state)
    bq = self._eval_behavior_quality(payloads.behavior_evidence, availabilities.get(DOMAIN_BEHAVIOR), p_state)
    iq = self._eval_identity_quality(payloads.identity_evidence, availabilities.get(DOMAIN_IDENTITY), p_state)
    mq = self._eval_metadata_quality(payloads.metadata_evidence, availabilities.get(DOMAIN_METADATA), p_state)

    return QualityScores(
        visual_quality=vq,
        voice_quality=aq,
        transcript_quality=tq,
        conversation_quality=cq,
        behavior_quality=bq,
        identity_quality=iq,
        metadata_quality=mq
    )

  def _eval_visual_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE or not p_state.camera_on:
      return 0.0
    if not ev:
      return p_state.visual_confidence

    face_visible = float(ev.get("face_visible", p_state.face_visible))
    face_size = float(ev.get("face_size_ratio", ev.get("face_size", 0.15)) or 0.0)
    tracking_conf = float(ev.get("tracking_confidence", ev.get("reliability", 0.85)) or 0.0)
    rec_conf = float(ev.get("recognition_confidence", ev.get("confidence", ev.get("score", 0.85))) or 0.0)

    # Combined visual quality weighted formula
    size_score = clamp(face_size / 0.15, 0.0, 1.0) if face_size > 0 else 0.5
    raw_q = (0.2 * float(face_visible) + 0.2 * size_score + 0.3 * tracking_conf + 0.3 * rec_conf)
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_voice_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE or not p_state.mic_on:
      return 0.0
    if not ev:
      return p_state.voice_confidence

    duration = float(ev.get("speech_duration_sec", ev.get("duration", 5.0)) or 0.0)
    diar_conf = float(ev.get("diarization_confidence", 0.85) or 0.0)
    speaker_conf = float(ev.get("speaker_recognition_confidence", ev.get("confidence", ev.get("score", 0.85))) or 0.0)
    vad_conf = float(ev.get("vad_confidence", 0.90) or 0.0)

    dur_score = clamp(duration / 5.0, 0.0, 1.0)
    raw_q = (0.25 * dur_score + 0.25 * diar_conf + 0.30 * speaker_conf + 0.20 * vad_conf)
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_transcript_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE or not p_state.transcript_available:
      return 0.0
    if not ev:
      return p_state.transcript_confidence

    whisper_conf = float(ev.get("whisper_confidence", ev.get("confidence", ev.get("reliability", 0.85))) or 0.0)
    completeness = float(ev.get("completeness", 0.90) or 0.0)
    is_final = bool(ev.get("is_final", ev.get("finalized", True)))

    final_mult = 1.0 if is_final else 0.75
    raw_q = (0.5 * whisper_conf + 0.5 * completeness) * final_mult
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_conversation_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE:
      return 0.0
    if not ev:
      return p_state.conversation_confidence

    coverage = float(ev.get("transcript_coverage", ev.get("coverage", 0.85)) or 0.0)
    reasoning_conf = float(ev.get("reasoning_confidence", ev.get("confidence", ev.get("score", 0.85))) or 0.0)

    raw_q = 0.4 * coverage + 0.6 * reasoning_conf
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_behavior_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE:
      return 0.0
    if not ev:
      return p_state.behavior_confidence

    data_count = float(ev.get("data_points_collected", ev.get("sample_count", 10)) or 0.0)
    reliability = float(ev.get("reliability", ev.get("confidence", 0.85)) or 0.0)

    count_score = clamp(data_count / 15.0, 0.0, 1.0)
    raw_q = 0.4 * count_score + 0.6 * reliability
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_identity_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE:
      return 0.0
    if not ev:
      return p_state.identity_confidence

    fuzzy = float(ev.get("fuzzy_score", ev.get("name_similarity", 0.85)) or 0.0)
    embedding = float(ev.get("embedding_similarity", ev.get("semantic_score", ev.get("score", 0.85))) or 0.0)

    raw_q = 0.4 * fuzzy + 0.6 * embedding
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)

  def _eval_metadata_quality(
      self,
      ev: Optional[Dict[str, Any]],
      status: Optional[EvidenceAvailability],
      p_state: UpstreamParticipantState
  ) -> float:
    if status == EvidenceAvailability.UNAVAILABLE:
      return 0.0
    if not ev:
      return p_state.metadata_confidence

    verified_email = 1.0 if ev.get("verified_email", True) else 0.5
    verified_participant = 1.0 if ev.get("verified_participant", True) else 0.6
    calendar_info = 1.0 if ev.get("calendar_info_present", ev.get("calendar_match", True)) else 0.7

    raw_q = 0.4 * verified_email + 0.3 * verified_participant + 0.3 * calendar_info
    if status == EvidenceAvailability.DEGRADED:
      raw_q *= 0.6
    return clamp(raw_q, 0.0, 1.0)
