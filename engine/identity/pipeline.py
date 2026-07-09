import logging
from typing import Optional

from engine.identity.schemas import (
    MeetingMetadata,
    ParticipantMetadata,
    IdentityEvidence,
)
from engine.identity.normalizer import NameNormalizer
from engine.identity.nickname_resolver import NicknameResolver
from engine.identity.email_matcher import EmailMatcher
from engine.identity.fuzzy_matcher import FuzzyMatcher
from engine.identity.metadata_matcher import MetadataMatcher
from engine.identity.semantic_matcher import SemanticMatcher
from engine.identity.scorer import IdentityScorer
from engine.identity.provider import IdentityEvidenceProvider
from engine.identity.participant_state import IdentityStateManager
from engine.identity.storage import IdentityStorageManager
from engine.identity.models import IdentityModelRegistry
from engine.identity.logger import measure_latency
from engine.identity.config import identity_config
from engine.identity.utils import now_ms

logger = logging.getLogger("SCIE.identity_engine.pipeline")


class IdentityPipeline:
  """Orchestrates the end-to-end Identity Evidence generation flow.

  Data flow::

      MeetingMetadata + ParticipantMetadata
        └─ NameNormalizer     (normalize candidate & participant names)
        └─ NicknameResolver   (expand candidate name → all alias variants)
        └─ EmailMatcher       (deterministic email comparison)
        └─ FuzzyMatcher       (RapidFuzz across all name variants)
        └─ MetadataMatcher    (display name, calendar title, recruiter signals)
        └─ SemanticMatcher    (Azure OpenAI text-embedding-3-large cosine sim)
        └─ IdentityScorer     (weighted evidence synthesis)
        └─ IdentityEvidenceProvider  (construct canonical IdentityEvidence)
        └─ IdentityStateManager      (update live Redis state)
        └─ IdentityStorageManager    (persist all 4 MongoDB collections)

  This pipeline does NOT identify the interview candidate.
  It only produces IdentityEvidence for the downstream Fusion Engine.
  """

  def __init__(self) -> None:
    self._normalizer = NameNormalizer()
    self._resolver = NicknameResolver()
    self._email_matcher = EmailMatcher()
    self._fuzzy_matcher = FuzzyMatcher()
    self._metadata_matcher = MetadataMatcher()
    self._semantic_matcher = SemanticMatcher()
    self._scorer = IdentityScorer()
    self._provider = IdentityEvidenceProvider()
    self._state_manager = IdentityStateManager()
    self._storage = IdentityStorageManager()
    # Ensure model registry is ready
    IdentityModelRegistry.get_instance().initialize()

  @measure_latency("identity_pipeline.process")
  async def process(
      self,
      meeting_metadata: MeetingMetadata,
      participant_metadata: ParticipantMetadata,
  ) -> Optional[IdentityEvidence]:
    """Processes a meeting+participant metadata pair into IdentityEvidence.

    Args:
        meeting_metadata: Meeting-level metadata with the expected candidate profile.
        participant_metadata: Observed participant metadata from the platform.

    Returns:
        A fully populated IdentityEvidence object, or None on catastrophic failure.
        Never raises; the pipeline always degrades gracefully.
    """
    try:
      logger.info(
          f"IdentityPipeline: Processing participant={participant_metadata.participant_id} "
          f"in meeting={meeting_metadata.meeting_id}"
      )
      timestamp = now_ms()

      # ── 0. Normalize names ──────────────────────────────────────────────
      norm_candidate = self._normalizer.normalize(meeting_metadata.candidate_name or "")
      norm_participant = self._normalizer.normalize(participant_metadata.display_name or "")
      logger.debug(
          f"IdentityPipeline: Normalized names — candidate='{norm_candidate}', "
          f"participant='{norm_participant}'"
      )

      # ── 1. Expand candidate aliases ─────────────────────────────────────
      candidate_variants = self._resolver.expand(meeting_metadata.candidate_name)

      # ── 2. Email matching ───────────────────────────────────────────────
      email_ev = self._email_matcher.match(
          candidate_email=meeting_metadata.candidate_email,
          participant_email=participant_metadata.email,
      )

      # ── 3. RapidFuzz matching ───────────────────────────────────────────
      fuzzy_ev = self._fuzzy_matcher.match(
          candidate_name=meeting_metadata.candidate_name,
          participant_name=participant_metadata.display_name,
          candidate_variants=candidate_variants,
      )

      # ── 4. Metadata matching ────────────────────────────────────────────
      metadata_ev = self._metadata_matcher.match(
          meeting_metadata=meeting_metadata,
          participant_metadata=participant_metadata,
      )

      # ── 5. Alias matching ───────────────────────────────────────────────
      alias_ev = self._resolver.match_alias(
          candidate_name=meeting_metadata.candidate_name,
          participant_name=participant_metadata.display_name,
      )

      # ── 6. Semantic matching (async, may be None if Azure OAI unavailable) ──
      semantic_ev = await self._semantic_matcher.match(
          candidate_text=norm_candidate or None,
          participant_text=norm_participant or None,
      )

      # ── 7. Score synthesis ──────────────────────────────────────────────
      overall_score, confidence, reasons = self._scorer.calculate(
          email_evidence=email_ev,
          fuzzy_evidence=fuzzy_ev,
          semantic_evidence=semantic_ev,
          alias_evidence=alias_ev,
          metadata_evidence=metadata_ev,
      )

      # ── 8. Construct canonical IdentityEvidence ─────────────────────────
      evidence = self._provider.provide(
          meeting_id=meeting_metadata.meeting_id,
          participant_id=participant_metadata.participant_id,
          overall_identity_score=overall_score,
          confidence=confidence,
          reasons=reasons,
          normalized_participant_name=norm_participant or None,
          normalized_candidate_name=norm_candidate or None,
          raw_display_name=participant_metadata.display_name,
          raw_candidate_name=meeting_metadata.candidate_name,
          candidate_email=meeting_metadata.candidate_email,
          participant_email=participant_metadata.email,
          email_evidence=email_ev,
          fuzzy_evidence=fuzzy_ev,
          semantic_evidence=semantic_ev,
          alias_evidence=alias_ev,
          metadata_evidence=metadata_ev,
      )

      # ── 9. Update Redis state ───────────────────────────────────────────
      existing_state = await self._state_manager.get_state(
          meeting_metadata.meeting_id,
          participant_metadata.participant_id,
      )
      await self._state_manager.save_state(evidence, existing_state)

      # ── 10. Persist to MongoDB ──────────────────────────────────────────
      await self._storage.save_evidence(evidence)
      await self._storage.upsert_profile(evidence)
      await self._storage.save_event(
          meeting_id=meeting_metadata.meeting_id,
          participant_id=participant_metadata.participant_id,
          event_type="identity_processed",
          payload={
              "overall_identity_score": overall_score,
              "confidence": confidence,
              "email_score": email_ev.score,
              "rapidfuzz_score": fuzzy_ev.score,
              "semantic_score": semantic_ev.score if semantic_ev else 0.0,
              "alias_score": alias_ev.score,
              "metadata_score": metadata_ev.score,
          },
          timestamp=timestamp,
      )

      # Record high-confidence matches in identity_matches
      if overall_score >= 0.70 and confidence >= 0.65:
        await self._storage.save_match(
            meeting_id=meeting_metadata.meeting_id,
            participant_id=participant_metadata.participant_id,
            matched_name=norm_candidate or "",
            matched_email=evidence.matched_email,
            score=overall_score,
            confidence=confidence,
            reasons=reasons[:5],
            timestamp=timestamp,
        )

      logger.info(
          f"IdentityPipeline: Completed for participant={participant_metadata.participant_id} "
          f"— score={overall_score:.4f}, conf={confidence:.4f}, evidence={evidence.evidence_id}"
      )
      return evidence

    except Exception as exc:
      logger.error(
          f"IdentityPipeline: Unhandled error for participant="
          f"{participant_metadata.participant_id} in meeting={meeting_metadata.meeting_id}: {exc}"
      )
      return None
