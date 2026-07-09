import logging
from typing import List, Optional

from engine.identity.schemas import (
    IdentityEvidence,
    EmailEvidence,
    FuzzyEvidence,
    SemanticEvidence,
    AliasEvidence,
    MetadataEvidence,
)
from engine.identity.utils import generate_evidence_id, now_ms

logger = logging.getLogger("SCIE.identity_engine.provider")


class IdentityEvidenceProvider:
  """Constructs the canonical ``IdentityEvidence`` output object.

  This is the final assembly step of the Identity Engine pipeline.
  It consolidates all sub-evidence objects, the computed score/confidence,
  and participant metadata into one structured, immutable evidence record
  ready for the downstream Evidence Fusion Engine.

  This module does NOT make candidate decisions.
  """

  def provide(
      self,
      meeting_id: str,
      participant_id: str,
      overall_identity_score: float,
      confidence: float,
      reasons: List[str],
      normalized_participant_name: Optional[str] = None,
      normalized_candidate_name: Optional[str] = None,
      raw_display_name: Optional[str] = None,
      raw_candidate_name: Optional[str] = None,
      candidate_email: Optional[str] = None,
      participant_email: Optional[str] = None,
      email_evidence: Optional[EmailEvidence] = None,
      fuzzy_evidence: Optional[FuzzyEvidence] = None,
      semantic_evidence: Optional[SemanticEvidence] = None,
      alias_evidence: Optional[AliasEvidence] = None,
      metadata_evidence: Optional[MetadataEvidence] = None,
  ) -> IdentityEvidence:
    """Assembles the canonical IdentityEvidence record.

    Args:
        meeting_id: Meeting identifier.
        participant_id: Participant identifier.
        overall_identity_score: Final weighted score from IdentityScorer.
        confidence: Final weighted confidence from IdentityScorer.
        reasons: Aggregated explanations from all matchers.
        normalized_participant_name: Canonical form of the display name.
        normalized_candidate_name: Canonical form of the candidate name.
        raw_display_name: Original display name (for auditability).
        raw_candidate_name: Original candidate name (for auditability).
        candidate_email: Expected candidate email.
        participant_email: Observed participant email.
        email_evidence: Sub-evidence from EmailMatcher.
        fuzzy_evidence: Sub-evidence from FuzzyMatcher.
        semantic_evidence: Sub-evidence from SemanticMatcher.
        alias_evidence: Sub-evidence from NicknameResolver.
        metadata_evidence: Sub-evidence from MetadataMatcher.

    Returns:
        Fully populated IdentityEvidence object.
    """
    # Derive individual scores from sub-evidences (0.0 if not available)
    email_score = email_evidence.score if email_evidence else 0.0
    fuzzy_score = fuzzy_evidence.score if fuzzy_evidence else 0.0
    semantic_score = semantic_evidence.score if semantic_evidence else 0.0
    alias_score = alias_evidence.score if alias_evidence else 0.0
    metadata_score = metadata_evidence.score if metadata_evidence else 0.0

    # Collect best-match details from sub-evidences
    matched_email = (email_evidence.candidate_email
                     if email_evidence and email_evidence.score > 0.0 else None)
    matched_alias = (alias_evidence.matched_alias
                     if alias_evidence and alias_evidence.score > 0.0 else None)
    matched_fields = (metadata_evidence.matched_fields
                      if metadata_evidence and metadata_evidence.matched_fields else [])

    # Sanitize reasons (remove empty strings, deduplicate preserving order)
    seen = set()
    clean_reasons = []
    for r in (reasons or []):
      if r and r not in seen:
        seen.add(r)
        clean_reasons.append(r)

    evidence = IdentityEvidence(
        evidence_id=generate_evidence_id(),
        meeting_id=meeting_id,
        participant_id=participant_id,
        normalized_participant_name=normalized_participant_name,
        normalized_candidate_name=normalized_candidate_name,
        raw_display_name=raw_display_name,
        raw_candidate_name=raw_candidate_name,
        candidate_email=candidate_email,
        participant_email=participant_email,
        email_score=round(email_score, 4),
        rapidfuzz_score=round(fuzzy_score, 4),
        semantic_score=round(semantic_score, 4),
        metadata_score=round(metadata_score, 4),
        alias_score=round(alias_score, 4),
        overall_identity_score=round(overall_identity_score, 4),
        confidence=round(confidence, 4),
        matched_alias=matched_alias,
        matched_email=matched_email,
        matched_fields=matched_fields,
        reasons=clean_reasons,
        email_evidence=email_evidence,
        fuzzy_evidence=fuzzy_evidence,
        semantic_evidence=semantic_evidence,
        alias_evidence=alias_evidence,
        metadata_evidence=metadata_evidence,
        timestamp=now_ms(),
    )

    logger.info(
        f"IdentityProvider: Produced IdentityEvidence {evidence.evidence_id} for "
        f"participant={participant_id} in meeting={meeting_id} — "
        f"score={evidence.overall_identity_score:.4f}, conf={evidence.confidence:.4f}"
    )
    return evidence
