"""
Dynamic Weight Rules Engine for the Dynamic Weighting Engine.

Applies modular, context-aware rule adjustments to domain weights before normalization:
- Camera Off: Visual = 0, scales up Voice, Transcript, Conversation.
- Microphone Muted: Voice = 0, scales up Visual, Behavior.
- Poor Face Quality: Reduces Visual.
- No Transcript: Transcript = 0, Conversation = 0.
- Strong Metadata Match: Increases Metadata weight.
- Very High Face / Voice Confidence: Increases specific domain weight.
- Poor Speaker Recognition: Reduces Voice.
- Screen Share Active: Increases Behavior weight.
- Long Meeting: Increases Conversation, reduces Metadata.

(`engine/weighting/rules.py`)
"""
from typing import Dict, List, Tuple
from engine.weighting.constants import (
    EvidenceAvailability,
    DOMAIN_VISUAL, DOMAIN_VOICE, DOMAIN_TRANSCRIPT,
    DOMAIN_CONVERSATION, DOMAIN_BEHAVIOR, DOMAIN_IDENTITY, DOMAIN_METADATA
)
from engine.weighting.config import weighting_config
from engine.weighting.models import DomainWeightItem, StrategyEvaluationContext
from engine.weighting.schemas import QualityScores


class DynamicRuleEngine:
  """Evaluates meeting context and signal quality to adjust raw domain weights dynamically."""

  def apply_rules(
      self,
      base_weights: Dict[str, float],
      availabilities: Dict[str, EvidenceAvailability],
      quality_scores: QualityScores,
      context: StrategyEvaluationContext
  ) -> Tuple[Dict[str, float], List[str]]:
    """Execute dynamic weighting rules and return modified raw weights and diagnostic reasons."""
    items: Dict[str, DomainWeightItem] = {}
    for dom, w in base_weights.items():
      avail = availabilities.get(dom, EvidenceAvailability.AVAILABLE)
      q = getattr(quality_scores, f"{dom}_quality", 1.0)
      items[dom] = DomainWeightItem(
          domain=dom,
          raw_base_weight=w,
          availability=avail,
          quality_score=q,
          adjusted_weight=w if avail in (EvidenceAvailability.AVAILABLE, EvidenceAvailability.DEGRADED) else 0.0
      )

    reasons: List[str] = []

    # 1. Availability Gates (Unavailable / Invalid -> 0.0)
    for dom, it in items.items():
      if it.availability in (EvidenceAvailability.UNAVAILABLE, EvidenceAvailability.INVALID):
        it.adjusted_weight = 0.0
        reasons.append(f"{dom.capitalize()} evidence unavailable -> weight set to 0.0")

    # 2. Camera Off Rule
    if not context.camera_on or not context.face_visible or items[DOMAIN_VISUAL].availability == EvidenceAvailability.UNAVAILABLE:
      items[DOMAIN_VISUAL].adjusted_weight = 0.0
      if not any("Camera off" in r for r in reasons):
        reasons.append("Camera off / face not visible -> Visual weight set to 0.0")
      # Increase voice, transcript, and conversation weights
      if items[DOMAIN_VOICE].adjusted_weight > 0:
        items[DOMAIN_VOICE].adjusted_weight *= 1.35
      if items[DOMAIN_TRANSCRIPT].adjusted_weight > 0:
        items[DOMAIN_TRANSCRIPT].adjusted_weight *= 1.25
      if items[DOMAIN_CONVERSATION].adjusted_weight > 0:
        items[DOMAIN_CONVERSATION].adjusted_weight *= 1.25

    # 3. Microphone Muted Rule
    if not context.mic_on or not context.voice_detected or items[DOMAIN_VOICE].availability == EvidenceAvailability.UNAVAILABLE:
      items[DOMAIN_VOICE].adjusted_weight = 0.0
      if not any("Microphone muted" in r for r in reasons):
        reasons.append("Microphone muted / voice not detected -> Voice weight set to 0.0")
      if items[DOMAIN_VISUAL].adjusted_weight > 0:
        items[DOMAIN_VISUAL].adjusted_weight *= 1.30
      if items[DOMAIN_BEHAVIOR].adjusted_weight > 0:
        items[DOMAIN_BEHAVIOR].adjusted_weight *= 1.25

    # 4. No Transcript Rule
    if not context.transcript_available or items[DOMAIN_TRANSCRIPT].availability == EvidenceAvailability.UNAVAILABLE:
      items[DOMAIN_TRANSCRIPT].adjusted_weight = 0.0
      if not any("No transcript available -> Transcript" in r for r in reasons):
        reasons.append("No transcript available -> Transcript weight set to 0.0")
      items[DOMAIN_CONVERSATION].adjusted_weight = 0.0
      if not any("No transcript available -> Conversation" in r for r in reasons):
        reasons.append("No transcript available -> Conversation weight set to 0.0")

    # 5. Quality-Driven Adjustments (Poor quality penalty / High quality boost)
    # Visual Quality Check
    if items[DOMAIN_VISUAL].adjusted_weight > 0:
      vq = quality_scores.visual_quality
      if vq < weighting_config.MIN_FACE_QUALITY:
        items[DOMAIN_VISUAL].adjusted_weight *= 0.50
        reasons.append(f"Poor face quality ({vq:.2f}) -> Visual weight reduced")
      elif vq > 0.90:
        items[DOMAIN_VISUAL].adjusted_weight *= 1.20
        reasons.append(f"Very high face recognition confidence ({vq:.2f}) -> Visual weight increased")

    # Voice Quality Check
    if items[DOMAIN_VOICE].adjusted_weight > 0:
      aq = quality_scores.voice_quality
      if aq < weighting_config.MIN_SPEECH_DIARIZATION_CONFIDENCE:
        items[DOMAIN_VOICE].adjusted_weight *= 0.50
        reasons.append(f"Poor speaker recognition/diarization ({aq:.2f}) -> Voice weight reduced")
      elif aq > 0.90:
        items[DOMAIN_VOICE].adjusted_weight *= 1.20
        reasons.append(f"Very high voice/speaker confidence ({aq:.2f}) -> Voice weight increased")

    # Strong Metadata Match Check
    if items[DOMAIN_METADATA].adjusted_weight > 0 and quality_scores.metadata_quality > 0.90:
      items[DOMAIN_METADATA].adjusted_weight *= 1.30
      reasons.append("Strong verified metadata/calendar match -> Metadata weight increased")

    # 6. Context Toggles: Screen Share Active
    if context.screen_share and items[DOMAIN_BEHAVIOR].adjusted_weight > 0:
      items[DOMAIN_BEHAVIOR].adjusted_weight *= 1.25
      reasons.append("Screen share active -> Behavior engagement weight increased slightly")

    # 7. Elapsed Time / Stage: Long Meeting Rule
    if context.elapsed_meeting_sec >= weighting_config.LONG_MEETING_DURATION_SEC:
      if items[DOMAIN_CONVERSATION].adjusted_weight > 0:
        items[DOMAIN_CONVERSATION].adjusted_weight *= 1.30
      if items[DOMAIN_METADATA].adjusted_weight > 0:
        items[DOMAIN_METADATA].adjusted_weight *= 0.50
      reasons.append("Long meeting duration (>15m) -> Conversation weight increased, Metadata influence reduced")

    # Extract adjusted raw weights map
    modified_weights = {dom: it.adjusted_weight for dom, it in items.items()}
    return modified_weights, reasons
