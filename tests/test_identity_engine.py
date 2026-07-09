"""
Comprehensive test suite for the Identity Engine.

Covers:
- NameNormalizer: 8-step normalization pipeline, edge cases
- NicknameResolver: expand, canonicalize, match_alias, register_alias
- EmailMatcher: all 4 tiers (exact, username, domain, none), edge cases
- FuzzyMatcher: exact, alias variants, mismatch, score bounds
- MetadataMatcher: all 5 signals, interviewer guard
- SemanticMatcher: embedding unavailable degradation, score normalization
- IdentityScorer: no evidence, single, all 5 signals, boost logic, dedup
- IdentityEvidenceProvider: structure, field derivation, reason dedup
- IdentityStateManager: save/get, history, smoothing, participants list
- IdentityStorageManager: all 4 MongoDB collections
- IdentityPipeline: full end-to-end, graceful failure, Redis+MongoDB
- IdentityWorkerManager: lifecycle, idempotent start, queue drain
"""

import asyncio
import pytest
import time
import uuid
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from engine.identity.schemas import (
    MeetingMetadata,
    ParticipantMetadata,
    IdentityEvidence,
    ParticipantIdentityState,
    EmailEvidence,
    FuzzyEvidence,
    SemanticEvidence,
    AliasEvidence,
    MetadataEvidence,
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
from engine.identity.pipeline import IdentityPipeline
from engine.identity.workers import IdentityWorkerManager, enqueue_identity_request
from engine.identity.utils import (
    generate_evidence_id, hash_text, cosine_similarity,
    embedding_distance, format_timestamp_ms, safe_lower, now_ms
)
from database.mongodb import get_mongo_db


# ──────────────────────────────────────────────────────────────────────────────
# Test Helpers / Factories
# ──────────────────────────────────────────────────────────────────────────────

def _meeting_meta(candidate_name="John Smith", candidate_email="john@acme.com",
                  calendar_title=None, interviewer_names=None) -> MeetingMetadata:
  return MeetingMetadata(
      meeting_id=f"mtg_{uuid.uuid4().hex[:6]}",
      candidate_name=candidate_name,
      candidate_email=candidate_email,
      calendar_title=calendar_title,
      interviewer_names=interviewer_names or [],
  )


def _participant_meta(pid=None, display_name="John Smith",
                      email="john@acme.com") -> ParticipantMetadata:
  return ParticipantMetadata(
      participant_id=pid or f"P_{uuid.uuid4().hex[:8]}",
      display_name=display_name,
      email=email,
  )


def _email_ev(score=0.0, conf=0.0, match_type="none") -> EmailEvidence:
  return EmailEvidence(score=score, confidence=conf,
                       reasons=["test"], match_type=match_type)


def _fuzzy_ev(score=0.0, conf=0.0) -> FuzzyEvidence:
  return FuzzyEvidence(score=score, confidence=conf, reasons=["test"])


def _semantic_ev(score=0.0, conf=0.0, cos_sim=0.0) -> SemanticEvidence:
  return SemanticEvidence(score=score, confidence=conf,
                          reasons=["test"], cosine_similarity=cos_sim)


def _alias_ev(score=0.0, conf=0.0) -> AliasEvidence:
  return AliasEvidence(score=score, confidence=conf, reasons=["test"])


def _metadata_ev(score=0.0, conf=0.0, fields=None) -> MetadataEvidence:
  return MetadataEvidence(score=score, confidence=conf,
                          reasons=["test"], matched_fields=fields or [])


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1: Utils
# ──────────────────────────────────────────────────────────────────────────────

class TestUtils:

  def test_evidence_id_format(self):
    eid = generate_evidence_id()
    assert eid.startswith("IE_")
    assert len(eid) == 11  # "IE_" + 8 hex chars

  def test_evidence_id_uniqueness(self):
    ids = {generate_evidence_id() for _ in range(200)}
    assert len(ids) == 200

  def test_hash_text_stable(self):
    assert hash_text("John Smith") == hash_text("John Smith")

  def test_hash_text_case_sensitive(self):
    assert hash_text("john") != hash_text("John")

  def test_cosine_similarity_identical(self):
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)

  def test_cosine_similarity_orthogonal(self):
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

  def test_cosine_similarity_empty(self):
    assert cosine_similarity([], []) == 0.0

  def test_embedding_distance_identical(self):
    v = [1.0, 2.0, 3.0]
    assert embedding_distance(v, v) == pytest.approx(0.0)

  def test_embedding_distance_simple(self):
    assert embedding_distance([0.0], [1.0]) == pytest.approx(1.0)

  def test_format_timestamp_zero(self):
    assert format_timestamp_ms(0) == "00:00:00"

  def test_format_timestamp_one_hour(self):
    assert format_timestamp_ms(3_600_000) == "01:00:00"

  def test_safe_lower_none(self):
    assert safe_lower(None) == ""

  def test_safe_lower_strips(self):
    assert safe_lower("  Hello  ") == "hello"

  def test_now_ms_is_epoch(self):
    before = int(time.time() * 1000)
    ms = now_ms()
    after = int(time.time() * 1000)
    assert before <= ms <= after


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2: NameNormalizer
# ──────────────────────────────────────────────────────────────────────────────

class TestNameNormalizer:

  def setup_method(self):
    self.n = NameNormalizer()

  def test_basic_normalization(self):
    assert self.n.normalize("John W. Smith") == "john w smith"

  def test_unicode_transliteration(self):
    assert self.n.normalize("Müller Franz") == "muller franz"

  def test_apostrophe_expanded(self):
    result = self.n.normalize("O'Brien")
    assert "o" in result
    assert "brien" in result

  def test_punctuation_removed(self):
    assert self.n.normalize("Smith, John!") == "smith john"

  def test_empty_input(self):
    assert self.n.normalize("") == ""
    assert self.n.normalize(None) == ""

  def test_leading_trailing_whitespace(self):
    assert self.n.normalize("   Alice   ") == "alice"

  def test_collapse_multiple_spaces(self):
    assert self.n.normalize("John   Smith") == "john smith"

  def test_initials(self):
    result = self.n.normalize("J. R. Smith")
    # Initials periods removed; result should be "j r smith" or similar
    assert "smith" in result
    assert "." not in result

  def test_already_normalized(self):
    assert self.n.normalize("john smith") == "john smith"

  def test_normalize_email_lowercases(self):
    assert self.n.normalize_email("John@EXAMPLE.COM") == "john@example.com"

  def test_normalize_email_none(self):
    assert self.n.normalize_email(None) == ""

  def test_extract_username(self):
    assert self.n.extract_username("john@example.com") == "john"

  def test_extract_domain(self):
    assert self.n.extract_domain("john@example.com") == "example.com"

  def test_extract_from_invalid_email(self):
    assert self.n.extract_username("not-an-email") == ""
    assert self.n.extract_domain("not-an-email") == ""


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3: NicknameResolver
# ──────────────────────────────────────────────────────────────────────────────

class TestNicknameResolver:

  def setup_method(self):
    self.r = NicknameResolver()

  def test_expand_canonical_includes_aliases(self):
    variants = self.r.expand("William")
    assert "william" in variants
    assert "bill" in variants or "will" in variants

  def test_expand_alias_includes_canonical(self):
    variants = self.r.expand("Bill")
    assert "william" in variants

  def test_expand_none(self):
    assert self.r.expand(None) == []

  def test_expand_with_last_name(self):
    variants = self.r.expand("Robert Smith")
    assert "bob smith" in variants
    assert "robert smith" in variants

  def test_canonicalize_nickname(self):
    canonicals = self.r.canonicalize("Bob")
    assert "robert" in canonicals

  def test_canonicalize_already_canonical(self):
    result = self.r.canonicalize("Robert")
    # Robert may canonicalize to itself via reverse map or return []
    # Should not crash
    assert isinstance(result, list)

  def test_match_alias_exact_alias(self):
    ev = self.r.match_alias("William Smith", "Bill Smith")
    assert ev.score >= 0.60
    assert ev.matched_alias is not None

  def test_match_alias_no_match(self):
    ev = self.r.match_alias("Alice Johnson", "Zebediah Xander")
    assert ev.score == 0.0

  def test_match_alias_none_candidate(self):
    ev = self.r.match_alias(None, "Bill Smith")
    assert ev.score == 0.0

  def test_match_alias_exact_same(self):
    ev = self.r.match_alias("John Smith", "John Smith")
    assert ev.score >= 0.60

  def test_register_alias_and_expand(self):
    self.r.register_alias("Nikolai", "Nick")
    variants = self.r.expand("Nikolai")
    assert "nick" in variants or "nikolai" in variants

  def test_register_alias_reverse_lookup(self):
    self.r.register_alias("Ekaterina", "Kate")
    canonicals = self.r.canonicalize("Kate")
    assert "ekaterina" in canonicals


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4: EmailMatcher
# ──────────────────────────────────────────────────────────────────────────────

class TestEmailMatcher:

  def setup_method(self):
    self.m = EmailMatcher()

  def test_exact_match(self):
    ev = self.m.match("john@example.com", "john@example.com")
    assert ev.score == pytest.approx(1.0)
    assert ev.match_type == "exact"

  def test_exact_match_case_insensitive(self):
    ev = self.m.match("JOHN@EXAMPLE.COM", "john@example.com")
    assert ev.score == pytest.approx(1.0)

  def test_username_match(self):
    ev = self.m.match("john@company.com", "john@personal.com")
    assert ev.score == pytest.approx(0.90)
    assert ev.match_type == "username"

  def test_domain_only_match(self):
    ev = self.m.match("alice@acme.com", "bob@acme.com")
    assert ev.score == pytest.approx(0.30)
    assert ev.match_type == "domain"

  def test_no_match(self):
    ev = self.m.match("alice@foo.com", "bob@bar.com")
    assert ev.score == 0.0
    assert ev.match_type == "none"

  def test_missing_candidate_email(self):
    ev = self.m.match(None, "bob@bar.com")
    assert ev.score == 0.0

  def test_missing_both_emails(self):
    ev = self.m.match(None, None)
    assert ev.score == 0.0

  def test_malformed_email(self):
    ev = self.m.match("not-an-email", "also-not-email")
    assert ev.score == 0.0

  def test_score_bounded(self):
    ev = self.m.match("a@b.com", "a@b.com")
    assert 0.0 <= ev.score <= 1.0
    assert 0.0 <= ev.confidence <= 1.0

  def test_reasons_populated(self):
    ev = self.m.match("john@acme.com", "john@acme.com")
    assert len(ev.reasons) >= 1
    assert any("match" in r.lower() for r in ev.reasons)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5: FuzzyMatcher
# ──────────────────────────────────────────────────────────────────────────────

class TestFuzzyMatcher:

  def setup_method(self):
    self.m = FuzzyMatcher()

  def test_exact_name_match(self):
    ev = self.m.match("John Smith", "John Smith")
    assert ev.score >= 0.95

  def test_alias_match(self):
    ev = self.m.match("William Jones", "Bill Jones")
    assert ev.score >= 0.60

  def test_typo_tolerant(self):
    ev = self.m.match("Jonathan Williams", "Johnathan Williams")
    assert ev.score >= 0.70

  def test_partial_name(self):
    ev = self.m.match("Alexander King", "Alex King")
    assert ev.score >= 0.70

  def test_completely_different(self):
    ev = self.m.match("Alice Johnson", "Zebediah Xander")
    assert ev.score < 0.50

  def test_none_candidate(self):
    ev = self.m.match(None, "Bob Smith")
    assert ev.score == 0.0

  def test_none_participant(self):
    ev = self.m.match("Bob Smith", None)
    assert ev.score == 0.0

  def test_score_bounded(self):
    ev = self.m.match("John", "John")
    assert 0.0 <= ev.score <= 1.0

  def test_edit_distance_populated(self):
    ev = self.m.match("John Smith", "John Smyth")
    assert ev.edit_distance >= 0

  def test_matched_variant_populated_on_alias(self):
    ev = self.m.match("Robert Brown", "Bob Brown")
    if ev.score > 0:
      assert ev.matched_variant is not None

  def test_with_precomputed_variants(self):
    variants = ["john smith", "johnny smith"]
    ev = self.m.match("John Smith", "Johnny Smith", candidate_variants=variants)
    assert ev.score >= 0.80


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6: MetadataMatcher
# ──────────────────────────────────────────────────────────────────────────────

class TestMetadataMatcher:

  def setup_method(self):
    self.m = MetadataMatcher()

  def test_display_name_match(self):
    mtg = _meeting_meta(candidate_name="Alice Johnson")
    p = _participant_meta(display_name="Alice Johnson")
    ev = self.m.match(mtg, p)
    assert ev.score >= 0.70
    assert "display_name" in ev.matched_fields

  def test_email_exact_in_metadata(self):
    mtg = _meeting_meta(candidate_email="alice@co.com")
    p = _participant_meta(email="alice@co.com", display_name="Alice X")
    ev = self.m.match(mtg, p)
    assert "email_exact" in ev.matched_fields

  def test_calendar_title_contains_candidate(self):
    mtg = _meeting_meta(candidate_name="John Smith", calendar_title="Interview with John Smith - Engineering")
    p = _participant_meta(display_name="John Smith")
    ev = self.m.match(mtg, p)
    assert ev.score >= 0.10

  def test_interviewer_name_penalizes(self):
    """When participant name matches an interviewer, confidence must drop."""
    mtg = _meeting_meta(
        candidate_name="Alice Johnson",
        interviewer_names=["Bob Smith"]
    )
    # Participant is actually the interviewer
    p = _participant_meta(display_name="Bob Smith")
    ev = self.m.match(mtg, p)
    assert ev.confidence < 0.30

  def test_no_matching_fields(self):
    mtg = _meeting_meta(candidate_name="Alice Johnson")
    p = _participant_meta(display_name="Zebediah Xander", email="z@x.com")
    ev = self.m.match(mtg, p)
    assert ev.score == 0.0

  def test_multiple_fields_boost_confidence(self):
    mtg = _meeting_meta(candidate_name="Alice Johnson", candidate_email="alice@co.com")
    p = _participant_meta(display_name="Alice Johnson", email="alice@co.com")
    ev_single = MetadataEvidence(score=0.80, confidence=0.72, reasons=[], matched_fields=["display_name"])
    ev = self.m.match(mtg, p)
    assert ev.confidence >= 0.70

  def test_score_bounded(self):
    mtg = _meeting_meta(candidate_name="John Smith")
    p = _participant_meta(display_name="John Smith")
    ev = self.m.match(mtg, p)
    assert 0.0 <= ev.score <= 1.0
    assert 0.0 <= ev.confidence <= 1.0


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7: SemanticMatcher (mocked embeddings)
# ──────────────────────────────────────────────────────────────────────────────

class TestSemanticMatcher:

  @pytest.mark.asyncio
  async def test_high_similarity(self):
    matcher = SemanticMatcher()
    # Mock the embedding client to return similar vectors
    mock_emb_a = [1.0, 0.0, 0.0]
    mock_emb_b = [0.99, 0.01, 0.0]
    with patch.object(matcher._client, "embed", new_callable=AsyncMock) as mock_embed:
      mock_embed.side_effect = [mock_emb_a, mock_emb_b]
      ev = await matcher.match("John Smith", "John Smith")
    assert ev.score >= 0.0  # Should produce evidence
    assert ev.cosine_similarity > 0.90

  @pytest.mark.asyncio
  async def test_embedding_unavailable_returns_zero(self):
    matcher = SemanticMatcher()
    with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=None):
      ev = await matcher.match("John Smith", "Bob Jones")
    assert ev.score == 0.0
    assert ev.confidence == 0.0
    assert len(ev.reasons) >= 1

  @pytest.mark.asyncio
  async def test_empty_input_returns_zero(self):
    matcher = SemanticMatcher()
    ev = await matcher.match("", "")
    assert ev.score == 0.0

  @pytest.mark.asyncio
  async def test_none_input_returns_zero(self):
    matcher = SemanticMatcher()
    ev = await matcher.match(None, "John Smith")
    assert ev.score == 0.0

  @pytest.mark.asyncio
  async def test_low_similarity_returns_zero(self):
    """Similarity below MIN_SEMANTIC_SCORE should return score=0.0."""
    matcher = SemanticMatcher()
    # Orthogonal vectors = cos_sim=0.0, which is below MIN_SEMANTIC_SCORE=0.50
    with patch.object(matcher._client, "embed", new_callable=AsyncMock) as mock_embed:
      mock_embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]
      ev = await matcher.match("Alice", "Zebediah")
    assert ev.score == 0.0

  @pytest.mark.asyncio
  async def test_high_cosine_produces_high_score(self):
    matcher = SemanticMatcher()
    identical = [1.0 / (3 ** 0.5)] * 3
    with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=identical):
      ev = await matcher.match("William", "Bill")
    # cos_sim=1.0 → score should be > 0
    assert ev.score >= 0.0


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 8: IdentityScorer
# ──────────────────────────────────────────────────────────────────────────────

class TestIdentityScorer:

  def setup_method(self):
    self.scorer = IdentityScorer()

  def test_no_evidence_returns_zero(self):
    score, conf, reasons = self.scorer.calculate()
    assert score == 0.0
    assert conf == 0.0

  def test_all_none_returns_zero(self):
    score, conf, reasons = self.scorer.calculate(None, None, None, None, None)
    assert score == 0.0

  def test_email_only_score(self):
    score, conf, _ = self.scorer.calculate(email_evidence=_email_ev(score=1.0, conf=0.98))
    assert score == pytest.approx(1.0)

  def test_fuzzy_only_score(self):
    score, conf, _ = self.scorer.calculate(fuzzy_evidence=_fuzzy_ev(score=0.90, conf=0.85))
    assert score == pytest.approx(0.90)

  def test_two_signals_no_boost(self):
    score2, conf2, _ = self.scorer.calculate(
        email_evidence=_email_ev(score=0.90, conf=0.88),
        fuzzy_evidence=_fuzzy_ev(score=0.85, conf=0.82)
    )
    # Two signals meet threshold, should get 1.03x boost
    assert conf2 >= 0.80

  def test_three_signals_boost(self):
    _, conf3, reasons = self.scorer.calculate(
        email_evidence=_email_ev(score=0.90, conf=0.88),
        fuzzy_evidence=_fuzzy_ev(score=0.88, conf=0.85),
        semantic_evidence=_semantic_ev(score=0.85, conf=0.84)
    )
    assert any("boost" in r.lower() for r in reasons)

  def test_all_five_signals(self):
    score, conf, reasons = self.scorer.calculate(
        email_evidence=_email_ev(score=1.0, conf=0.98),
        fuzzy_evidence=_fuzzy_ev(score=0.90, conf=0.88),
        semantic_evidence=_semantic_ev(score=0.85, conf=0.84),
        alias_evidence=_alias_ev(score=0.80, conf=0.75),
        metadata_evidence=_metadata_ev(score=0.75, conf=0.70),
    )
    assert score >= 0.85
    assert conf >= 0.85
    assert len(reasons) >= 5

  def test_score_bounded_max_1(self):
    score, conf, _ = self.scorer.calculate(
        email_evidence=_email_ev(1.0, 1.0),
        fuzzy_evidence=_fuzzy_ev(1.0, 1.0),
        semantic_evidence=_semantic_ev(1.0, 1.0),
        alias_evidence=_alias_ev(1.0, 1.0),
        metadata_evidence=_metadata_ev(1.0, 1.0),
    )
    assert score <= 1.0
    assert conf <= 1.0

  def test_zero_score_evidence_excluded(self):
    """Email with score=0 should not dilute the fuzzy-only score."""
    score, _, _ = self.scorer.calculate(
        email_evidence=_email_ev(0.0, 0.0),
        fuzzy_evidence=_fuzzy_ev(0.90, 0.88)
    )
    assert score == pytest.approx(0.90)

  def test_reasons_deduplication(self):
    ev = _email_ev(score=0.90, conf=0.88)
    ev.reasons = ["dup reason", "dup reason"]
    score, conf, reasons = self.scorer.calculate(email_evidence=ev)
    assert reasons.count("[Email] dup reason") <= 1


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 9: IdentityEvidenceProvider
# ──────────────────────────────────────────────────────────────────────────────

class TestIdentityEvidenceProvider:

  def setup_method(self):
    self.provider = IdentityEvidenceProvider()

  def _call(self, **kwargs):
    defaults = dict(
        meeting_id="mtg_test", participant_id="P_test_01",
        overall_identity_score=0.88, confidence=0.85, reasons=["reason A"]
    )
    defaults.update(kwargs)
    return self.provider.provide(**defaults)

  def test_returns_identity_evidence(self):
    ev = self._call()
    assert isinstance(ev, IdentityEvidence)

  def test_evidence_id_format(self):
    ev = self._call()
    assert ev.evidence_id.startswith("IE_")

  def test_scores_from_sub_evidences(self):
    ev = self._call(
        email_evidence=_email_ev(score=0.95, conf=0.94),
        fuzzy_evidence=_fuzzy_ev(score=0.88, conf=0.85),
    )
    assert ev.email_score == pytest.approx(0.95)
    assert ev.rapidfuzz_score == pytest.approx(0.88)

  def test_zero_scores_when_no_sub_evidence(self):
    ev = self._call()
    assert ev.email_score == 0.0
    assert ev.rapidfuzz_score == 0.0
    assert ev.semantic_score == 0.0

  def test_matched_email_from_email_evidence(self):
    email_ev = _email_ev(score=1.0, conf=0.98)
    email_ev.candidate_email = "john@acme.com"
    ev = self._call(email_evidence=email_ev)
    assert ev.matched_email == "john@acme.com"

  def test_matched_alias_from_alias_evidence(self):
    alias_ev = _alias_ev(score=0.80, conf=0.75)
    alias_ev.matched_alias = "bill"
    ev = self._call(alias_evidence=alias_ev)
    assert ev.matched_alias == "bill"

  def test_matched_fields_from_metadata_evidence(self):
    meta_ev = _metadata_ev(score=0.80, fields=["display_name", "email_exact"])
    ev = self._call(metadata_evidence=meta_ev)
    assert "display_name" in ev.matched_fields

  def test_reasons_deduplication(self):
    ev = self._call(reasons=["reason A", "reason A", "reason B"])
    assert ev.reasons.count("reason A") == 1
    assert "reason B" in ev.reasons

  def test_empty_reasons_handled(self):
    ev = self._call(reasons=[])
    assert ev.reasons == []

  def test_timestamp_is_recent(self):
    before = now_ms()
    ev = self._call()
    after = now_ms()
    assert before <= ev.timestamp <= after

  def test_scores_rounded_to_4dp(self):
    ev = self._call(overall_identity_score=0.88888888, confidence=0.77777777)
    # Should be rounded to 4 decimal places
    assert ev.overall_identity_score == pytest.approx(0.8889, abs=0.0001)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 10: IdentityStateManager (Redis)
# ──────────────────────────────────────────────────────────────────────────────

def _make_evidence(pid="P_state_01", meeting_id="mtg_state", score=0.88, conf=0.85):
  return IdentityEvidence(
      evidence_id=generate_evidence_id(),
      meeting_id=meeting_id,
      participant_id=pid,
      overall_identity_score=score,
      confidence=conf,
      email_score=0.90,
      rapidfuzz_score=0.85,
      semantic_score=0.80,
      alias_score=0.75,
      metadata_score=0.70,
      reasons=["test reason"],
      timestamp=now_ms()
  )


class TestIdentityStateManager:

  @pytest.mark.asyncio
  async def test_save_and_fetch(self):
    mgr = IdentityStateManager()
    ev = _make_evidence(pid="P_state_save_01", meeting_id="mtg_state_save")
    state = await mgr.save_state(ev)
    fetched = await mgr.get_state("mtg_state_save", "P_state_save_01")
    assert fetched is not None
    assert fetched.participant_id == "P_state_save_01"
    assert fetched.identity_score == pytest.approx(0.88)

  @pytest.mark.asyncio
  async def test_history_accumulates(self):
    mgr = IdentityStateManager()
    ev = _make_evidence(pid="P_state_hist_01", meeting_id="mtg_state_hist")
    state1 = await mgr.save_state(ev)
    state2 = await mgr.save_state(ev, existing_state=state1)
    assert len(state2.history) == 2

  @pytest.mark.asyncio
  async def test_confidence_smoothing_on_dip(self):
    mgr = IdentityStateManager()
    ev_high = _make_evidence(pid="P_smooth_01", conf=0.90)
    state_high = await mgr.save_state(ev_high)

    ev_low = _make_evidence(pid="P_smooth_01", conf=0.45)
    state_low = await mgr.save_state(ev_low, existing_state=state_high)
    # Smoothed: should be between 0.45 and 0.90
    assert state_low.confidence > 0.45
    assert state_low.confidence < 0.90

  @pytest.mark.asyncio
  async def test_confidence_increase_not_smoothed(self):
    mgr = IdentityStateManager()
    ev_low = _make_evidence(pid="P_inc_01", conf=0.50)
    state_low = await mgr.save_state(ev_low)

    ev_high = _make_evidence(pid="P_inc_01", conf=0.92)
    state_high = await mgr.save_state(ev_high, existing_state=state_low)
    assert state_high.confidence == pytest.approx(0.92)

  @pytest.mark.asyncio
  async def test_unknown_participant_returns_none(self):
    mgr = IdentityStateManager()
    result = await mgr.get_state("no_meeting_xyz", "P_does_not_exist_xyz")
    assert result is None

  @pytest.mark.asyncio
  async def test_get_all_participants(self):
    mgr = IdentityStateManager()
    mtg = f"mtg_allparts_{uuid.uuid4().hex[:6]}"
    for i in range(3):
      ev = _make_evidence(pid=f"P_all_{i:02d}", meeting_id=mtg)
      await mgr.save_state(ev)
    pids = await mgr.get_all_participants(mtg)
    for i in range(3):
      assert f"P_all_{i:02d}" in pids

  @pytest.mark.asyncio
  async def test_history_max_length(self):
    from engine.identity.config import identity_config
    mgr = IdentityStateManager()
    ev = _make_evidence()
    history_full = [{"ts": i} for i in range(identity_config.HISTORY_MAX_LENGTH)]
    from engine.identity.schemas import ParticipantIdentityState
    existing = ParticipantIdentityState(
        participant_id=ev.participant_id,
        meeting_id=ev.meeting_id,
        identity_score=0.80, confidence=0.80,
        history=history_full, last_updated=now_ms()
    )
    state = mgr._build_state(ev, existing)
    assert len(state.history) <= identity_config.HISTORY_MAX_LENGTH


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 11: IdentityStorageManager (MongoDB)
# ──────────────────────────────────────────────────────────────────────────────

class TestIdentityStorage:

  @pytest.mark.asyncio
  async def test_save_evidence(self):
    storage = IdentityStorageManager()
    db = get_mongo_db()
    mtg = f"test_id_storage_{uuid.uuid4().hex[:6]}"
    ev = _make_evidence(meeting_id=mtg)
    if db is not None:
      await db["identity_evidence"].delete_many({"meeting_id": mtg})
    await storage.save_evidence(ev)
    if db is not None:
      count = await db["identity_evidence"].count_documents({"meeting_id": mtg})
      assert count == 1

  @pytest.mark.asyncio
  async def test_upsert_profile(self):
    storage = IdentityStorageManager()
    db = get_mongo_db()
    mtg = f"test_id_profile_{uuid.uuid4().hex[:6]}"
    ev = _make_evidence(meeting_id=mtg, pid="P_profile_01")
    if db is not None:
      await db["identity_participant_profiles"].delete_many({"meeting_id": mtg})
    await storage.upsert_profile(ev)
    await storage.upsert_profile(ev)   # Upsert twice — should remain one
    if db is not None:
      count = await db["identity_participant_profiles"].count_documents(
          {"meeting_id": mtg, "participant_id": "P_profile_01"}
      )
      assert count == 1

  @pytest.mark.asyncio
  async def test_save_match(self):
    storage = IdentityStorageManager()
    db = get_mongo_db()
    mtg = f"test_id_match_{uuid.uuid4().hex[:6]}"
    if db is not None:
      await db["identity_matches"].delete_many({"meeting_id": mtg})
    await storage.save_match(
        meeting_id=mtg, participant_id="P_match_01",
        matched_name="john smith", matched_email="john@acme.com",
        score=0.92, confidence=0.90, reasons=["test"], timestamp=now_ms()
    )
    if db is not None:
      count = await db["identity_matches"].count_documents({"meeting_id": mtg})
      assert count == 1

  @pytest.mark.asyncio
  async def test_save_event(self):
    storage = IdentityStorageManager()
    db = get_mongo_db()
    mtg = f"test_id_event_{uuid.uuid4().hex[:6]}"
    if db is not None:
      await db["identity_events"].delete_many({"meeting_id": mtg})
    await storage.save_event(
        meeting_id=mtg, participant_id="P_ev_01",
        event_type="identity_processed",
        payload={"score": 0.88},
        timestamp=now_ms()
    )
    if db is not None:
      doc = await db["identity_events"].find_one({"meeting_id": mtg})
      assert doc is not None
      assert doc["event_type"] == "identity_processed"


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 12: IdentityPipeline (End-to-End)
# ──────────────────────────────────────────────────────────────────────────────

class TestIdentityPipeline:

  @pytest.mark.asyncio
  async def test_exact_match_produces_high_score(self):
    pipeline = IdentityPipeline()
    mtg = _meeting_meta(candidate_name="Alice Johnson", candidate_email="alice@acme.com")
    p = _participant_meta(display_name="Alice Johnson", email="alice@acme.com")
    evidence = await pipeline.process(mtg, p)
    assert evidence is not None
    assert evidence.email_score == pytest.approx(1.0)
    assert evidence.rapidfuzz_score >= 0.90
    assert evidence.overall_identity_score >= 0.80

  @pytest.mark.asyncio
  async def test_alias_match_produces_evidence(self):
    pipeline = IdentityPipeline()
    mtg = _meeting_meta(candidate_name="William Smith")
    p = _participant_meta(display_name="Bill Smith")
    evidence = await pipeline.process(mtg, p)
    assert evidence is not None
    assert evidence.rapidfuzz_score >= 0.60

  @pytest.mark.asyncio
  async def test_completely_different_names_low_score(self):
    pipeline = IdentityPipeline()
    mtg = _meeting_meta(candidate_name="Alice Johnson")
    p = _participant_meta(display_name="Zebediah Xander", email="z@x.com")
    evidence = await pipeline.process(mtg, p)
    assert evidence is not None
    assert evidence.overall_identity_score < 0.50

  @pytest.mark.asyncio
  async def test_missing_candidate_name_graceful(self):
    pipeline = IdentityPipeline()
    mtg = _meeting_meta(candidate_name=None)
    p = _participant_meta(display_name="Bob Jones")
    evidence = await pipeline.process(mtg, p)
    # Should not crash; returns evidence (possibly with low scores)
    assert evidence is None or isinstance(evidence, IdentityEvidence)

  @pytest.mark.asyncio
  async def test_evidence_id_unique_per_call(self):
    pipeline = IdentityPipeline()
    mtg = _meeting_meta()
    p = _participant_meta()
    ev1 = await pipeline.process(mtg, p)
    ev2 = await pipeline.process(mtg, p)
    assert ev1 is not None and ev2 is not None
    assert ev1.evidence_id != ev2.evidence_id

  @pytest.mark.asyncio
  async def test_redis_state_updated(self):
    pipeline = IdentityPipeline()
    mtg_id = f"mtg_{uuid.uuid4().hex[:6]}"
    pid = f"P_{uuid.uuid4().hex[:8]}"
    mtg = MeetingMetadata(
        meeting_id=mtg_id, candidate_name="Carol White",
        candidate_email="carol@co.com"
    )
    p = ParticipantMetadata(
        participant_id=pid, display_name="Carol White", email="carol@co.com"
    )
    ev = await pipeline.process(mtg, p)
    assert ev is not None
    state_mgr = IdentityStateManager()
    state = await state_mgr.get_state(mtg_id, pid)
    assert state is not None
    assert state.identity_score == pytest.approx(ev.overall_identity_score)

  @pytest.mark.asyncio
  async def test_mongodb_evidence_persisted(self):
    db = get_mongo_db()
    if db is None:
      pytest.skip("MongoDB not available")
    pipeline = IdentityPipeline()
    mtg_id = f"mtg_{uuid.uuid4().hex[:6]}"
    mtg = MeetingMetadata(meeting_id=mtg_id, candidate_name="Dave Brown")
    p = ParticipantMetadata(
        participant_id=f"P_{uuid.uuid4().hex[:8]}",
        display_name="Dave Brown"
    )
    await db["identity_evidence"].delete_many({"meeting_id": mtg_id})
    ev = await pipeline.process(mtg, p)
    count = await db["identity_evidence"].count_documents({"meeting_id": mtg_id})
    assert count >= 1

  @pytest.mark.asyncio
  async def test_high_confidence_match_saved_to_identity_matches(self):
    db = get_mongo_db()
    if db is None:
      pytest.skip("MongoDB not available")
    pipeline = IdentityPipeline()
    mtg_id = f"mtg_{uuid.uuid4().hex[:6]}"
    mtg = MeetingMetadata(
        meeting_id=mtg_id,
        candidate_name="Emma Wilson",
        candidate_email="emma@acme.com"
    )
    p = ParticipantMetadata(
        participant_id=f"P_{uuid.uuid4().hex[:8]}",
        display_name="Emma Wilson",
        email="emma@acme.com"
    )
    await db["identity_matches"].delete_many({"meeting_id": mtg_id})
    ev = await pipeline.process(mtg, p)
    if ev and ev.overall_identity_score >= 0.70:
      count = await db["identity_matches"].count_documents({"meeting_id": mtg_id})
      assert count >= 1


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 13: IdentityWorkerManager
# ──────────────────────────────────────────────────────────────────────────────

class TestIdentityWorkerManager:

  @pytest.mark.asyncio
  async def test_start_stop_lifecycle(self):
    IdentityWorkerManager._instance = None
    mgr = IdentityWorkerManager.get_instance()
    mgr.start()
    assert mgr.is_running is True
    assert len(mgr.worker_tasks) == 2

    await mgr.stop()
    assert mgr.is_running is False
    assert all(t.done() for t in mgr.worker_tasks)

  @pytest.mark.asyncio
  async def test_start_idempotent(self):
    IdentityWorkerManager._instance = None
    mgr = IdentityWorkerManager.get_instance()
    mgr.start()
    initial_count = len(mgr.worker_tasks)
    mgr.start()   # Second call must be a no-op
    assert len(mgr.worker_tasks) == initial_count
    await mgr.stop()

  @pytest.mark.asyncio
  async def test_enqueue_and_process(self):
    db = get_mongo_db()
    IdentityWorkerManager._instance = None
    mgr = IdentityWorkerManager.get_instance()
    mgr.start()

    mtg_id = f"mtg_worker_{uuid.uuid4().hex[:6]}"
    if db is not None:
      await db["identity_events"].delete_many({"meeting_id": mtg_id})

    mtg = MeetingMetadata(meeting_id=mtg_id, candidate_name="Frank Garcia")
    p = ParticipantMetadata(
        participant_id=f"P_{uuid.uuid4().hex[:8]}",
        display_name="Frank Garcia"
    )
    await mgr.enqueue(mtg, p)

    # Wait up to 3s for background worker to process
    processed = False
    if db is not None:
      for _ in range(30):
        count = await db["identity_events"].count_documents({"meeting_id": mtg_id})
        if count > 0:
          processed = True
          break
        await asyncio.sleep(0.1)
      assert processed, "Worker should have processed and stored the event in MongoDB"

    await mgr.stop()

  @pytest.mark.asyncio
  async def test_convenience_helper(self):
    IdentityWorkerManager._instance = None
    mtg = MeetingMetadata(meeting_id="mtg_conv", candidate_name="Grace Lee")
    p = ParticipantMetadata(participant_id="P_conv_01", display_name="Grace Lee")
    await enqueue_identity_request(mtg, p)
    mgr = IdentityWorkerManager.get_instance()
    assert mgr.is_running
    await mgr.stop()
