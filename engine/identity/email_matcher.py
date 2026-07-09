import logging
from typing import Optional

from engine.identity.normalizer import NameNormalizer
from engine.identity.config import identity_config
from engine.identity.schemas import EmailEvidence
from engine.identity.exceptions import EmailMatcherError

logger = logging.getLogger("SCIE.identity_engine.email_matcher")


class EmailMatcher:
  """Deterministic email comparison producing structured EmailEvidence.

  Scoring matrix (all thresholds configurable via ``identity_config``):

  =========  =============================================================
  Score      Condition
  =========  =============================================================
  1.00       Exact lowercase match after normalization.
  0.90       Same username (local-part before ``@``), different domain.
  0.30       Same domain only, different usernames.
  0.00       Completely different or one/both emails missing.
  =========  =============================================================

  This matcher makes NO candidate decisions.  It only returns evidence.
  """

  def __init__(self) -> None:
    self._normalizer = NameNormalizer()

  def match(
      self,
      candidate_email: Optional[str],
      participant_email: Optional[str],
  ) -> EmailEvidence:
    """Compares candidate email against participant email.

    Args:
        candidate_email: Expected email from meeting / calendar metadata.
        participant_email: Observed email from the participant list or DOM.

    Returns:
        EmailEvidence containing score, confidence, match_type, and reasons.

    Raises:
        EmailMatcherError: If the comparison fails due to an unexpected error.
    """
    try:
      if not candidate_email or not participant_email:
        missing = []
        if not candidate_email:
          missing.append("candidate email")
        if not participant_email:
          missing.append("participant email")
        return EmailEvidence(
            score=0.0,
            confidence=0.0,
            reasons=[f"Missing {' and '.join(missing)} — cannot compare."],
            match_type="none",
            candidate_email=candidate_email,
            participant_email=participant_email
        )

      c_norm = self._normalizer.normalize_email(candidate_email)
      p_norm = self._normalizer.normalize_email(participant_email)

      if not c_norm or not p_norm:
        return EmailEvidence(
            score=0.0, confidence=0.0,
            reasons=["One or both emails are malformed after normalization."],
            match_type="none"
        )

      # ── 1. Exact match ─────────────────────────────────────────────────────
      if c_norm == p_norm:
        score = identity_config.EMAIL_EXACT_SCORE
        return EmailEvidence(
            score=score,
            confidence=min(1.0, score * 0.98),
            reasons=[f"Exact email match: '{c_norm}'"],
            match_type="exact",
            candidate_email=c_norm,
            participant_email=p_norm
        )

      c_user = self._normalizer.extract_username(c_norm)
      p_user = self._normalizer.extract_username(p_norm)
      c_domain = self._normalizer.extract_domain(c_norm)
      p_domain = self._normalizer.extract_domain(p_norm)

      # ── 2. Same username, different domain ─────────────────────────────────
      if c_user and p_user and c_user == p_user:
        score = identity_config.EMAIL_USERNAME_MATCH_SCORE
        return EmailEvidence(
            score=score,
            confidence=min(1.0, score * 0.90),
            reasons=[
                f"Username match: '{c_user}' (candidate: {c_norm}, participant: {p_norm})"
            ],
            match_type="username",
            candidate_email=c_norm,
            participant_email=p_norm
        )

      # ── 3. Same domain only ────────────────────────────────────────────────
      if c_domain and p_domain and c_domain == p_domain:
        score = identity_config.EMAIL_DOMAIN_ONLY_SCORE
        return EmailEvidence(
            score=score,
            confidence=min(1.0, score * 0.70),
            reasons=[
                f"Shared domain only: '@{c_domain}' (no username match)"
            ],
            match_type="domain",
            candidate_email=c_norm,
            participant_email=p_norm
        )

      # ── 4. No match ────────────────────────────────────────────────────────
      return EmailEvidence(
          score=0.0,
          confidence=0.0,
          reasons=[f"No email match: '{c_norm}' vs '{p_norm}'"],
          match_type="none",
          candidate_email=c_norm,
          participant_email=p_norm
      )

    except Exception as exc:
      raise EmailMatcherError(f"EmailMatcher failed: {exc}") from exc
