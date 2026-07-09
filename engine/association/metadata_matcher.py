import logging
from typing import List, Optional
from rapidfuzz import fuzz

from engine.association.schemas import MetadataMatchEvidence, MeetingMetadata
from engine.association.config import association_config
from engine.association.utils import clean_string
from engine.association.models import AssociationModelRegistry
from engine.association.exceptions import MetadataMatcherError

logger = logging.getLogger("SCIE.association_engine.metadata_matcher")


class MetadataMatcher:
  """Compares incoming metadata (name, display name, email, calendar info)
  against target participant profiles using RapidFuzz and optional sentence embeddings.

  Does NOT make identity decisions; only emits MetadataMatchEvidence with scores,
  confidence, and specific match reasons.
  """

  def match(
      self,
      target_name: Optional[str],
      target_email: Optional[str],
      target_nicknames: Optional[List[str]],
      meeting_metadata: MeetingMetadata,
  ) -> MetadataMatchEvidence:
    """Evaluates similarity between target profile and meeting metadata."""
    try:
      scores: List[float] = []
      reasons: List[str] = []
      matched_name: Optional[str] = None
      matched_email: Optional[str] = None

      # 1. Email exact / substring matching
      if target_email and meeting_metadata.email:
        t_email = clean_string(target_email)
        m_email = clean_string(meeting_metadata.email)
        if t_email == m_email and t_email != "":
          scores.append(1.0)
          reasons.append(f"Exact email match: {meeting_metadata.email}")
          matched_email = meeting_metadata.email
        elif t_email.split('@')[0] == m_email.split('@')[0] and t_email != "":
          scores.append(0.85)
          reasons.append(f"Email prefix match: {meeting_metadata.email}")
          matched_email = meeting_metadata.email

      # 2. Candidate / Display Name fuzzy matching
      registry = AssociationModelRegistry.get_instance()
      names_to_test = [meeting_metadata.candidate_name, meeting_metadata.display_name]
      names_to_test.extend(meeting_metadata.nicknames)
      names_to_test = [n for n in names_to_test if n]

      target_names = [target_name]
      if target_nicknames:
        target_names.extend(target_nicknames)
      target_names = [n for n in target_names if n]

      # If no target name/email assigned yet on this participant, adopt metadata profile
      if not target_names and not target_email and (names_to_test or meeting_metadata.email):
        adopted_name = meeting_metadata.display_name or meeting_metadata.candidate_name or (names_to_test[0] if names_to_test else None)
        return MetadataMatchEvidence(
            score=0.85,
            confidence=0.80,
            reasons=[f"Adopted candidate profile from meeting metadata: '{adopted_name}' ({meeting_metadata.email})"],
            matched_name=adopted_name,
            matched_email=meeting_metadata.email,
            similarity_metric="metadata_adoption"
        )

      best_name_score = 0.0
      for t_name in target_names:
        for m_name in names_to_test:
          clean_t = clean_string(t_name)
          clean_m = clean_string(m_name)
          if not clean_t or not clean_m:
            continue

          # Check optional sentence embedding similarity first if available
          emb_sim = registry.compute_text_similarity(t_name, m_name)
          if emb_sim is not None and emb_sim > best_name_score:
            best_name_score = emb_sim
            matched_name = m_name
            reasons.append(f"Semantic embedding match '{t_name}' ~ '{m_name}' ({emb_sim:.2f})")
            continue

          # RapidFuzz deterministic WRatio & token_sort_ratio
          wratio = fuzz.WRatio(clean_t, clean_m) / 100.0
          token_ratio = fuzz.token_sort_ratio(clean_t, clean_m) / 100.0
          partial = fuzz.partial_ratio(clean_t, clean_m) / 100.0
          combined_sim = max(wratio, token_ratio, (partial * 0.9))

          if combined_sim > best_name_score:
            best_name_score = combined_sim
            matched_name = m_name

      if best_name_score > 0.0:
        scores.append(best_name_score)
        if best_name_score >= association_config.MIN_METADATA_SIMILARITY:
          reasons.append(f"High name similarity match: '{matched_name}' (score: {best_name_score:.2f})")
        else:
          reasons.append(f"Low name similarity match: '{matched_name}' (score: {best_name_score:.2f})")

      if not scores:
        return MetadataMatchEvidence(
            score=0.0,
            confidence=0.0,
            reasons=["No matching email or name attributes found in metadata."]
        )

      avg_score = sum(scores) / len(scores)
      # Confidence boosts if both email and name matched
      confidence = min(1.0, avg_score * (1.2 if len(scores) > 1 else 0.9))

      logger.debug(
          f"MetadataMatcher: score={avg_score:.2f}, conf={confidence:.2f}, reasons={reasons}"
      )
      return MetadataMatchEvidence(
          score=round(avg_score, 4),
          confidence=round(confidence, 4),
          reasons=reasons,
          matched_name=matched_name,
          matched_email=matched_email,
          similarity_metric="rapidfuzz_plus_exact"
      )

    except Exception as exc:
      raise MetadataMatcherError(f"Failed to execute MetadataMatcher: {exc}") from exc
