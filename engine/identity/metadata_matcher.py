import logging
from typing import List, Optional

from rapidfuzz import fuzz

from engine.identity.normalizer import NameNormalizer
from engine.identity.nickname_resolver import NicknameResolver
from engine.identity.config import identity_config
from engine.identity.schemas import (
    MeetingMetadata,
    ParticipantMetadata,
    MetadataEvidence,
)
from engine.identity.exceptions import MetadataMatcherError

logger = logging.getLogger("SCIE.identity_engine.metadata_matcher")


class MetadataMatcher:
  """Compares participant metadata against meeting-level candidate metadata.

  Evaluates multiple corroborating signals beyond just name and email:
  - Display name similarity (RapidFuzz)
  - Calendar title containment
  - Recruiter / interviewer name presence
  - Job title relevance
  - Metadata field count (more fields matched = higher confidence)

  Returns structured MetadataEvidence with a score, confidence, and a list
  of which fields matched.

  Does NOT make candidate decisions.
  """

  def __init__(self) -> None:
    self._normalizer = NameNormalizer()
    self._resolver = NicknameResolver()

  def match(
      self,
      meeting_metadata: MeetingMetadata,
      participant_metadata: ParticipantMetadata,
  ) -> MetadataEvidence:
    """Evaluates all available metadata signals and returns evidence.

    Args:
        meeting_metadata: Meeting-level metadata containing the expected
            candidate profile.
        participant_metadata: Observed participant metadata from the platform.

    Returns:
        MetadataEvidence with aggregated score, confidence, matched fields,
        and human-readable reasons.

    Raises:
        MetadataMatcherError: If the operation fails unexpectedly.
    """
    try:
      scores: List[float] = []
      reasons: List[str] = []
      matched_fields: List[str] = []

      norm_candidate = self._normalizer.normalize(meeting_metadata.candidate_name or "")
      norm_participant = self._normalizer.normalize(participant_metadata.display_name or "")

      # ── 1. Display name fuzzy match ──────────────────────────────────────
      if norm_candidate and norm_participant:
        wratio = fuzz.WRatio(norm_candidate, norm_participant) / 100.0
        if wratio >= 0.70:
          scores.append(wratio)
          matched_fields.append("display_name")
          reasons.append(
              f"Display name fuzzy match: '{norm_participant}' ~ '{norm_candidate}' "
              f"(WRatio={wratio:.2f})"
          )

      # ── 2. Email match (binary check; detailed scoring in EmailMatcher) ──
      if meeting_metadata.candidate_email and participant_metadata.email:
        c_email = self._normalizer.normalize_email(meeting_metadata.candidate_email)
        p_email = self._normalizer.normalize_email(participant_metadata.email)
        if c_email == p_email:
          scores.append(1.0)
          matched_fields.append("email_exact")
          reasons.append(f"Exact email match in metadata: '{c_email}'")
        elif c_email.split("@")[0] == p_email.split("@")[0]:
          scores.append(0.85)
          matched_fields.append("email_username")
          reasons.append(f"Email username match in metadata: '{c_email.split('@')[0]}'")

      # ── 3. Calendar title containment ────────────────────────────────────
      if meeting_metadata.calendar_title and norm_candidate:
        norm_title = self._normalizer.normalize(meeting_metadata.calendar_title)
        # Check if candidate name tokens appear in the calendar title
        candidate_tokens = norm_candidate.split()
        title_tokens = norm_title.split()
        matched_cal_tokens = [t for t in candidate_tokens if t in title_tokens and len(t) > 2]
        if matched_cal_tokens:
          cal_score = min(0.65, len(matched_cal_tokens) / max(1, len(candidate_tokens)) * 0.75)
          scores.append(cal_score)
          matched_fields.append("calendar_title")
          reasons.append(
              f"Calendar title contains candidate tokens: {matched_cal_tokens} "
              f"(score={cal_score:.2f})"
          )

      # ── 4. Alias match via NicknameResolver ──────────────────────────────
      if meeting_metadata.candidate_name and participant_metadata.display_name:
        alias_ev = self._resolver.match_alias(
            meeting_metadata.candidate_name, participant_metadata.display_name
        )
        if alias_ev.score > 0.0:
          scores.append(alias_ev.score * 0.75)  # Weight alias lower in metadata context
          matched_fields.append("alias")
          reasons.extend(alias_ev.reasons)

      # ── 5. Interviewer / recruiter name NOT matching ──────────────────────
      # Guard: if participant name matches an interviewer, reduce confidence
      interviewer_match = False
      if meeting_metadata.interviewer_names and norm_participant:
        for iname in meeting_metadata.interviewer_names:
          norm_iname = self._normalizer.normalize(iname)
          if norm_iname and fuzz.WRatio(norm_participant, norm_iname) / 100.0 >= 0.85:
            interviewer_match = True
            reasons.append(
                f"WARNING: Participant '{norm_participant}' matches interviewer '{norm_iname}' "
                f"— NOT the candidate."
            )
            break

      if not scores:
        return MetadataEvidence(
            score=0.0, confidence=0.0,
            reasons=["No metadata fields matched between candidate and participant profiles."],
            matched_fields=[]
        )

      avg_score = sum(scores) / len(scores)

      # Interviewer match penalty: halve confidence if interviewer name matched
      if interviewer_match:
        avg_score = avg_score * 0.20
        reasons.append("Interviewer name match detected — confidence heavily penalized.")

      # Multi-field boost: more matching fields → higher confidence
      field_boost = 1.0 + (len(matched_fields) - 1) * 0.05
      confidence = round(min(1.0, avg_score * field_boost * 0.92), 4)

      logger.debug(
          f"MetadataMatcher: score={avg_score:.4f}, conf={confidence:.4f}, "
          f"fields={matched_fields}"
      )

      return MetadataEvidence(
          score=round(avg_score, 4),
          confidence=confidence,
          reasons=reasons,
          matched_fields=matched_fields
      )

    except Exception as exc:
      raise MetadataMatcherError(f"MetadataMatcher failed: {exc}") from exc
