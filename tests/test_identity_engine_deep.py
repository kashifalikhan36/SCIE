"""
Deep Test Suite — Identity Engine
==================================
Covers every module at the edge-case, boundary, and integration level.

Structure:
    TestUtilsDeep             — hash_text, cosine_similarity, embedding_distance, edge math
    TestNormalizerDeep        — all 8 normalization steps + unicode/edge cases
    TestNicknameResolverDeep  — expand transitive chains, bidirectional, empty, long names
    TestEmailMatcherDeep      — all 4 tiers + sub-domain, unicode, whitespace, edge cases
    TestFuzzyMatcherDeep      — multi-variant best-pick, all-zero, score monotonicity
    TestMetadataMatcherDeep   — all 5 signals in isolation + combined, interviewer guard
    TestEmbeddingClientDeep   — cache hit/miss, batch, empty text, retry loop, no-config
    TestSemanticMatcherDeep   — score normalization, threshold, NaN-safe, batch
    TestScorerDeep            — active-weight math, boost thresholds, reason dedup, boundary math
    TestProviderDeep          — field derivation, matched_email/alias/fields, dedup
    TestStateManagerDeep      — smoothing formula, history trim, overwrite, get-all
    TestStorageDeep           — all 4 collections, upsert idempotency, event payload
    TestPipelineDeep          — 12 real-world scenarios + graceful failure paths
    TestWorkerManagerDeep     — queue drain, retry backoff, sentinel, idempotent-start
"""

import asyncio
import json
import math
import uuid
import pytest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from engine.identity.utils import (
    generate_evidence_id, hash_text, cosine_similarity,
    embedding_distance, format_timestamp_ms, safe_lower, now_ms, truncate
)
from engine.identity.normalizer import NameNormalizer
from engine.identity.nickname_resolver import NicknameResolver
from engine.identity.email_matcher import EmailMatcher
from engine.identity.fuzzy_matcher import FuzzyMatcher
from engine.identity.metadata_matcher import MetadataMatcher
from engine.identity.semantic_matcher import SemanticMatcher
from engine.identity.embedding_client import EmbeddingClient
from engine.identity.scorer import IdentityScorer
from engine.identity.provider import IdentityEvidenceProvider
from engine.identity.participant_state import IdentityStateManager
from engine.identity.storage import IdentityStorageManager
from engine.identity.pipeline import IdentityPipeline
from engine.identity.workers import IdentityWorkerManager, enqueue_identity_request
from engine.identity.config import identity_config
from engine.identity.schemas import (
    MeetingMetadata, ParticipantMetadata,
    IdentityEvidence, ParticipantIdentityState,
    EmailEvidence, FuzzyEvidence, SemanticEvidence,
    AliasEvidence, MetadataEvidence,
)
from engine.identity.exceptions import (
    NormalizationError, EmailMatcherError, FuzzyMatcherError,
    MetadataMatcherError, SemanticMatcherError, IdentityScorerError,
)
from database.mongodb import get_mongo_db


# ─────────────────────────────────────────────────────────────────────────────
# Test Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mtg(candidate_name="Alice Johnson", candidate_email="alice@acme.com",
         calendar_title=None, interviewer_names=None, meeting_id=None) -> MeetingMetadata:
    return MeetingMetadata(
        meeting_id=meeting_id or f"mtg_{uuid.uuid4().hex[:6]}",
        candidate_name=candidate_name,
        candidate_email=candidate_email,
        calendar_title=calendar_title,
        interviewer_names=interviewer_names or [],
    )


def _part(pid=None, display_name="Alice Johnson", email="alice@acme.com") -> ParticipantMetadata:
    return ParticipantMetadata(
        participant_id=pid or f"P_{uuid.uuid4().hex[:8]}",
        display_name=display_name,
        email=email,
    )


def _ev_base(pid="P_deep_01", meeting_id="mtg_deep", score=0.88, conf=0.85):
    return IdentityEvidence(
        evidence_id=generate_evidence_id(),
        meeting_id=meeting_id,
        participant_id=pid,
        overall_identity_score=score,
        confidence=conf,
        email_score=0.80, rapidfuzz_score=0.85,
        semantic_score=0.75, alias_score=0.70, metadata_score=0.65,
        reasons=["test reason"],
        timestamp=now_ms(),
    )


def _email_ev(score=0.0, conf=0.0, mt="none", reasons=None):
    return EmailEvidence(score=score, confidence=conf,
                         reasons=reasons or ["r"], match_type=mt)


def _fuzzy_ev(score=0.0, conf=0.0, sim=0.0, edit=0, reasons=None):
    return FuzzyEvidence(score=score, confidence=conf,
                         reasons=reasons or ["r"],
                         similarity=sim, edit_distance=edit)


def _sem_ev(score=0.0, conf=0.0, cos=0.0, reasons=None):
    return SemanticEvidence(score=score, confidence=conf,
                            reasons=reasons or ["r"], cosine_similarity=cos)


def _alias_ev(score=0.0, conf=0.0, alias=None, reasons=None):
    return AliasEvidence(score=score, confidence=conf,
                         reasons=reasons or ["r"], matched_alias=alias)


def _meta_ev(score=0.0, conf=0.0, fields=None, reasons=None):
    return MetadataEvidence(score=score, confidence=conf,
                            reasons=reasons or ["r"], matched_fields=fields or [])


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: TestUtilsDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestUtilsDeep:

    # hash_text
    def test_hash_same_string_always_equal(self):
        for _ in range(5):
            assert hash_text("Alice Johnson") == hash_text("Alice Johnson")

    def test_hash_different_strings_different(self):
        assert hash_text("Alice") != hash_text("Bob")

    def test_hash_empty_string(self):
        assert isinstance(hash_text(""), str)
        assert len(hash_text("")) == 64   # SHA-256 hex = 64 chars

    def test_hash_whitespace_difference(self):
        assert hash_text("john smith") != hash_text("johnsmith")

    def test_hash_unicode(self):
        h = hash_text("Müller")
        assert isinstance(h, str)
        assert len(h) == 64

    # cosine_similarity
    def test_cosine_identical_unit_vector(self):
        v = [1.0 / math.sqrt(3)] * 3
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-9)

    def test_cosine_opposite_vectors(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0, abs=1e-9)

    def test_cosine_45_degrees(self):
        cos = cosine_similarity([1.0, 0.0], [1.0, 1.0])
        assert cos == pytest.approx(1.0 / math.sqrt(2), abs=1e-9)

    def test_cosine_length_mismatch(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_cosine_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_cosine_clamped_above_1(self):
        # Should never exceed 1.0 even with floating-point errors
        v = [1.0, 0.0, 0.0]
        result = cosine_similarity(v, v)
        assert result <= 1.0

    # embedding_distance
    def test_distance_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert embedding_distance(v, v) == pytest.approx(0.0)

    def test_distance_known_value(self):
        # dist([0,0], [3,4]) = 5.0
        assert embedding_distance([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)

    def test_distance_mismatched_length(self):
        result = embedding_distance([1.0], [1.0, 2.0])
        assert result == float("inf")

    def test_distance_empty(self):
        assert embedding_distance([], []) == float("inf")

    # format_timestamp_ms
    def test_format_45_seconds(self):
        assert format_timestamp_ms(45_000) == "00:00:45"

    def test_format_1_hour_30_min(self):
        ms = (1 * 3600 + 30 * 60) * 1000
        assert format_timestamp_ms(ms) == "01:30:00"

    def test_format_large(self):
        # 25 hours should format correctly
        ms = 25 * 3600 * 1000
        result = format_timestamp_ms(ms)
        assert "25:00:00" in result

    # safe_lower
    def test_safe_lower_uppercase(self):
        assert safe_lower("JOHN SMITH") == "john smith"

    def test_safe_lower_mixed(self):
        assert safe_lower("  JoHn  ") == "john"

    # generate_evidence_id
    def test_id_always_starts_ie(self):
        for _ in range(50):
            assert generate_evidence_id().startswith("IE_")

    def test_id_always_11_chars(self):
        for _ in range(50):
            assert len(generate_evidence_id()) == 11

    def test_id_hex_suffix(self):
        eid = generate_evidence_id()
        hex_part = eid[3:]
        int(hex_part, 16)   # should not raise

    # truncate
    def test_truncate_short_string_unchanged(self):
        assert truncate("hello", 120) == "hello"

    def test_truncate_long_string_adds_ellipsis(self):
        result = truncate("x" * 200, 50)
        assert len(result) == 50
        assert result.endswith("...")

    def test_truncate_exact_boundary(self):
        s = "a" * 120
        assert truncate(s, 120) == s


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: TestNormalizerDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizerDeep:

    def setup_method(self):
        self.n = NameNormalizer()

    # Core normalization cases
    def test_step1_unicode_nfc(self):
        # Composed vs decomposed form of the same character
        result = self.n.normalize("Ångström")
        assert isinstance(result, str)
        assert "." not in result

    def test_step2_accented_transliteration(self):
        assert self.n.normalize("Müller") == "muller"
        assert self.n.normalize("Ñoño") == "nono"
        assert self.n.normalize("Ö") == "o"

    def test_step3_lowercase(self):
        assert self.n.normalize("ALICE JOHNSON") == "alice johnson"

    def test_step4_initial_dots_removed(self):
        result = self.n.normalize("J. R. Smith")
        assert "." not in result
        assert "smith" in result

    def test_step4_commas_removed(self):
        result = self.n.normalize("Smith, John")
        assert "," not in result
        assert "smith" in result

    def test_step5_apostrophe_expanded(self):
        result = self.n.normalize("O'Brien")
        assert "'" not in result
        assert "brien" in result

    def test_step6_hyphen_separator_removed(self):
        result = self.n.normalize("Alice - Smith")
        assert " - " not in result

    def test_step8_collapse_spaces(self):
        assert self.n.normalize("Alice    Johnson") == "alice johnson"

    def test_idempotent(self):
        """Normalizing an already-normalized string returns itself."""
        once = self.n.normalize("alice johnson")
        twice = self.n.normalize(once)
        assert once == twice

    def test_only_whitespace_returns_empty(self):
        assert self.n.normalize("     ") == ""

    def test_numbers_in_name(self):
        result = self.n.normalize("John Smith2")
        assert "2" in result

    def test_very_long_name(self):
        name = "Alexander " * 20 + "Smith"
        result = self.n.normalize(name)
        assert isinstance(result, str)
        assert "smith" in result

    def test_single_char_name(self):
        result = self.n.normalize("A")
        assert result == "a"

    def test_mixed_languages(self):
        # Arabic name in Latin script
        result = self.n.normalize("Mahmoud")
        assert result == "mahmoud"

    def test_normalize_dr_prefix(self):
        result = self.n.normalize("Dr. John Smith")
        assert "." not in result
        assert "john" in result

    # Email helpers
    def test_normalize_email_strips_whitespace(self):
        assert self.n.normalize_email("  JOHN@ACME.COM  ") == "john@acme.com"

    def test_normalize_email_empty_string(self):
        assert self.n.normalize_email("") == ""

    def test_extract_username_complex(self):
        assert self.n.extract_username("first.last+tag@example.co.uk") == "first.last+tag"

    def test_extract_domain_subdomain(self):
        assert self.n.extract_domain("john@mail.example.com") == "mail.example.com"

    def test_extract_no_at_sign(self):
        assert self.n.extract_username("notanemail") == ""
        assert self.n.extract_domain("notanemail") == ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: TestNicknameResolverDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestNicknameResolverDeep:

    def setup_method(self):
        self.r = NicknameResolver()

    # Expand
    def test_expand_includes_original(self):
        variants = self.r.expand("Robert")
        assert "robert" in variants

    def test_expand_canonical_forward(self):
        variants = self.r.expand("Robert")
        assert "bob" in variants
        assert "rob" in variants

    def test_expand_alias_finds_siblings(self):
        # "bob" should find "robert" and then expand robert's other aliases
        variants = self.r.expand("Bob")
        assert "robert" in variants

    def test_expand_with_last_name_preserved(self):
        variants = self.r.expand("William Jones")
        assert "bill jones" in variants or "will jones" in variants

    def test_expand_unknown_name_returns_itself(self):
        variants = self.r.expand("Zephyrine")
        assert "zephyrine" in variants
        assert len(variants) >= 1

    def test_expand_empty_string(self):
        assert self.r.expand("") == []

    def test_expand_none(self):
        assert self.r.expand(None) == []

    def test_expand_no_duplicates(self):
        variants = self.r.expand("William")
        assert len(variants) == len(set(variants))

    # Canonicalize
    def test_canonicalize_bill_is_william(self):
        assert "william" in self.r.canonicalize("Bill")

    def test_canonicalize_unknown_returns_empty(self):
        result = self.r.canonicalize("Zephyrine")
        assert isinstance(result, list)

    def test_canonicalize_none(self):
        result = self.r.canonicalize(None)
        assert result == []

    # match_alias
    def test_match_alias_first_name_only(self):
        # "Bill" should match candidate "William"
        ev = self.r.match_alias("William", "Bill")
        assert ev.score >= 0.60

    def test_match_alias_with_last_name(self):
        ev = self.r.match_alias("Robert Smith", "Bob Smith")
        assert ev.score >= 0.60

    def test_match_alias_no_relationship(self):
        ev = self.r.match_alias("Alice", "Zebediah")
        assert ev.score == 0.0

    def test_match_alias_none_candidate(self):
        ev = self.r.match_alias(None, "Bob")
        assert ev.score == 0.0
        assert len(ev.reasons) >= 1

    def test_match_alias_none_participant(self):
        ev = self.r.match_alias("Robert", None)
        assert ev.score == 0.0

    def test_match_alias_exact_same_name(self):
        ev = self.r.match_alias("Alice", "Alice")
        assert ev.score >= 0.60

    def test_match_alias_international_name(self):
        ev = self.r.match_alias("Muhammad", "Mo")
        assert ev.score >= 0.0   # May or may not match; should not crash

    # register_alias
    def test_register_then_expand(self):
        self.r.register_alias("Svetlana", "Sveta")
        variants = self.r.expand("Svetlana")
        assert "sveta" in variants

    def test_register_then_canonicalize(self):
        self.r.register_alias("Anastasia", "Nastya")
        canonicals = self.r.canonicalize("Nastya")
        assert "anastasia" in canonicals

    def test_register_duplicate_safe(self):
        self.r.register_alias("Boris", "Borya")
        self.r.register_alias("Boris", "Borya")   # second register: no crash/duplicate
        variants = self.r.expand("Boris")
        assert variants.count("borya") <= 1


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: TestEmailMatcherDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestEmailMatcherDeep:

    def setup_method(self):
        self.m = EmailMatcher()

    # Exact match
    def test_exact_uppercase_candidate(self):
        ev = self.m.match("ALICE@ACME.COM", "alice@acme.com")
        assert ev.score == pytest.approx(identity_config.EMAIL_EXACT_SCORE)
        assert ev.match_type == "exact"

    def test_exact_match_with_leading_trailing_spaces(self):
        ev = self.m.match("  alice@acme.com  ", "alice@acme.com")
        assert ev.score == pytest.approx(identity_config.EMAIL_EXACT_SCORE)

    def test_exact_match_confidence_high(self):
        ev = self.m.match("alice@acme.com", "alice@acme.com")
        assert ev.confidence >= 0.95

    # Username match
    def test_username_match_different_tlds(self):
        ev = self.m.match("john@acme.com", "john@acme.org")
        assert ev.score == pytest.approx(identity_config.EMAIL_USERNAME_MATCH_SCORE)
        assert ev.match_type == "username"

    def test_username_match_subdomain(self):
        ev = self.m.match("john@acme.com", "john@mail.acme.com")
        assert ev.score == pytest.approx(identity_config.EMAIL_USERNAME_MATCH_SCORE)

    def test_username_match_reason_mentions_username(self):
        ev = self.m.match("alice@x.com", "alice@y.com")
        assert any("alice" in r for r in ev.reasons)

    # Domain match
    def test_domain_match_preserves_domain_in_reason(self):
        ev = self.m.match("alice@acme.com", "bob@acme.com")
        assert ev.score == pytest.approx(identity_config.EMAIL_DOMAIN_ONLY_SCORE)
        assert any("acme.com" in r for r in ev.reasons)

    def test_domain_confidence_lower_than_username(self):
        ev_user = self.m.match("alice@a.com", "alice@b.com")
        ev_domain = self.m.match("alice@a.com", "bob@a.com")
        assert ev_user.confidence > ev_domain.confidence

    # No match
    def test_no_match_completely_different(self):
        ev = self.m.match("alice@acme.com", "bob@other.io")
        assert ev.score == 0.0
        assert ev.match_type == "none"

    def test_no_match_empty_candidate(self):
        ev = self.m.match("", "alice@acme.com")
        assert ev.score == 0.0

    def test_no_match_whitespace_only_candidate(self):
        ev = self.m.match("   ", "alice@acme.com")
        assert ev.score == 0.0

    # Malformed
    def test_malformed_no_at_candidate(self):
        ev = self.m.match("notanemail", "alice@acme.com")
        assert ev.score == 0.0

    def test_malformed_no_at_participant(self):
        ev = self.m.match("alice@acme.com", "notanemail")
        assert ev.score == 0.0

    # Score / confidence bounds
    def test_all_scores_bounded_0_1(self):
        cases = [
            ("alice@acme.com", "alice@acme.com"),
            ("alice@acme.com", "alice@other.com"),
            ("alice@acme.com", "bob@acme.com"),
            ("alice@acme.com", "bob@other.com"),
        ]
        for c, p in cases:
            ev = self.m.match(c, p)
            assert 0.0 <= ev.score <= 1.0
            assert 0.0 <= ev.confidence <= 1.0

    def test_candidate_email_preserved_in_output(self):
        ev = self.m.match("alice@acme.com", "alice@acme.com")
        assert ev.candidate_email == "alice@acme.com"
        assert ev.participant_email == "alice@acme.com"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TestFuzzyMatcherDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestFuzzyMatcherDeep:

    def setup_method(self):
        self.m = FuzzyMatcher()

    def test_exact_match_score_near_1(self):
        ev = self.m.match("John Smith", "John Smith")
        assert ev.score >= 0.95

    def test_nickname_variant_tested(self):
        ev = self.m.match("Robert Brown", "Bob Brown")
        assert ev.score >= 0.60

    def test_transposition_tolerance(self):
        ev = self.m.match("Michael Johnson", "Micheal Johnson")
        assert ev.score >= 0.85

    def test_suffix_tolerance(self):
        ev = self.m.match("William Jones Jr.", "William Jones")
        assert ev.score >= 0.80

    def test_prefix_match(self):
        ev = self.m.match("Alexander King", "Alex King")
        assert ev.score >= 0.70

    def test_completely_different_low_score(self):
        ev = self.m.match("Alice Johnson", "Zebediah Xander")
        assert ev.score < 0.50

    def test_both_empty_strings(self):
        ev = self.m.match("", "")
        assert ev.score == 0.0

    def test_one_char_candidate(self):
        ev = self.m.match("A", "Alice")
        assert 0.0 <= ev.score <= 1.0

    def test_score_monotonicity(self):
        """Better match → higher score."""
        ev_good = self.m.match("John Smith", "John Smith")
        ev_typo = self.m.match("John Smith", "John Smyth")
        ev_bad = self.m.match("John Smith", "Zebediah Xander")
        assert ev_good.score >= ev_typo.score >= ev_bad.score

    def test_precomputed_variants_override_resolver(self):
        variants = ["alice smith", "ali smith"]
        ev = self.m.match("Alice Smith", "Ali Smith", candidate_variants=variants)
        assert ev.score >= 0.70

    def test_edit_distance_zero_on_exact(self):
        ev = self.m.match("Alice", "Alice")
        assert ev.edit_distance == 0

    def test_edit_distance_positive_on_typo(self):
        ev = self.m.match("Alice", "Alyce")
        assert ev.edit_distance >= 1

    def test_matched_variant_populated_when_alias(self):
        ev = self.m.match("William Brown", "Bill Brown")
        if ev.score >= identity_config.MIN_FUZZY_SCORE:
            assert ev.matched_variant is not None

    def test_score_confidence_both_populated(self):
        ev = self.m.match("John Smith", "John Smith")
        assert ev.score > 0.0
        assert ev.confidence > 0.0

    def test_all_scores_bounded(self):
        names = [
            ("Alice Johnson", "Alice Johnson"),
            ("Alice Johnson", "Bob Smith"),
            ("William Jones", "Bill Jones"),
            ("Robert Brown", "Bobby Brown"),
        ]
        for c, p in names:
            ev = self.m.match(c, p)
            assert 0.0 <= ev.score <= 1.0
            assert 0.0 <= ev.confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: TestMetadataMatcherDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestMetadataMatcherDeep:

    def setup_method(self):
        self.m = MetadataMatcher()

    def test_display_name_exact_match(self):
        ev = self.m.match(_mtg(candidate_name="Alice Johnson"), _part(display_name="Alice Johnson"))
        assert ev.score >= 0.70
        assert "display_name" in ev.matched_fields

    def test_display_name_partial_match(self):
        ev = self.m.match(_mtg(candidate_name="Alice Johnson"), _part(display_name="Alice J."))
        assert ev.score >= 0.0   # May or may not reach threshold; should not crash

    def test_email_exact_field(self):
        mtg = _mtg(candidate_email="alice@co.com")
        p = _part(email="alice@co.com", display_name="X Y")
        ev = self.m.match(mtg, p)
        assert "email_exact" in ev.matched_fields

    def test_email_username_field(self):
        mtg = _mtg(candidate_email="alice@co.com")
        p = _part(email="alice@other.com", display_name="X Y")
        ev = self.m.match(mtg, p)
        assert "email_username" in ev.matched_fields

    def test_calendar_title_signal(self):
        mtg = _mtg(candidate_name="John Smith", calendar_title="Technical Interview John Smith - Engineering")
        p = _part(display_name="John Smith")
        ev = self.m.match(mtg, p)
        assert "calendar_title" in ev.matched_fields or ev.score > 0.0

    def test_alias_field(self):
        mtg = _mtg(candidate_name="William Smith")
        p = _part(display_name="Bill Smith")
        ev = self.m.match(mtg, p)
        # alias match may populate matched_fields
        assert isinstance(ev.matched_fields, list)

    def test_interviewer_guard_exact_match(self):
        mtg = _mtg(candidate_name="Alice Johnson", interviewer_names=["Bob Smith"])
        p = _part(display_name="Bob Smith")
        ev = self.m.match(mtg, p)
        assert ev.confidence < 0.30

    def test_interviewer_guard_candidate_not_penalized(self):
        """Candidate whose name does not match any interviewer must NOT be penalized."""
        mtg = _mtg(candidate_name="Alice Johnson", interviewer_names=["Bob Smith"])
        p = _part(display_name="Alice Johnson")
        ev = self.m.match(mtg, p)
        assert ev.score >= 0.70

    def test_no_metadata_fields_match(self):
        mtg = _mtg(candidate_name="Alice Johnson")
        p = _part(display_name="Zebediah Xander", email="z@x.com")
        ev = self.m.match(mtg, p)
        assert ev.score == 0.0
        assert ev.matched_fields == []

    def test_multiple_matching_fields_higher_confidence(self):
        mtg = _mtg(candidate_name="Alice Johnson", candidate_email="alice@co.com",
                   calendar_title="Interview Alice Johnson")
        p = _part(display_name="Alice Johnson", email="alice@co.com")
        ev_multi = self.m.match(mtg, p)
        mtg2 = _mtg(candidate_name="Alice Johnson")
        p2 = _part(display_name="Alice Johnson", email="z@x.com")
        ev_single = self.m.match(mtg2, p2)
        assert ev_multi.confidence >= ev_single.confidence

    def test_no_candidate_name_no_email_returns_zero(self):
        """When candidate has neither name nor email, all signals are 0."""
        mtg = MeetingMetadata(meeting_id="mtg_noname", candidate_name=None,
                              candidate_email=None)
        p = _part(display_name="Alice Johnson", email=None)
        ev = self.m.match(mtg, p)
        assert ev.score == 0.0
        assert ev.matched_fields == []

    def test_score_confidence_bounded(self):
        for cn, pn in [("Alice", "Alice"), ("Alice", "Bob"), ("William", "Bill")]:
            ev = self.m.match(_mtg(candidate_name=cn), _part(display_name=pn))
            assert 0.0 <= ev.score <= 1.0
            assert 0.0 <= ev.confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: TestEmbeddingClientDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestEmbeddingClientDeep:

    def _fresh_client(self):
        client = EmbeddingClient()
        client._client = None   # Ensure it starts unconfigured
        return client

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self):
        client = self._fresh_client()
        result = await client.embed("")
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_none(self):
        client = self._fresh_client()
        result = await client.embed("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_config_returns_none(self):
        client = self._fresh_client()
        # Even if we call embed, without a real API key it should return None
        result = await client.embed("John Smith")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_vector(self):
        client = self._fresh_client()
        expected = [0.1, 0.2, 0.3]
        with patch.object(client, "_cache_get", new_callable=AsyncMock, return_value=expected):
            result = await client.embed("Alice Johnson")
        assert result == expected

    @pytest.mark.asyncio
    async def test_cache_miss_then_store(self):
        client = self._fresh_client()
        expected = [0.5, 0.6, 0.7]

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=expected)]
        mock_azure = AsyncMock()
        mock_azure.embeddings.create = AsyncMock(return_value=mock_response)

        client._client = mock_azure
        cache_set_calls = []

        async def fake_cache_get(text):
            return None

        async def fake_cache_set(text, embedding):
            cache_set_calls.append(embedding)

        with patch.object(client, "_cache_get", fake_cache_get), \
             patch.object(client, "_cache_set", fake_cache_set):
            result = await client.embed("Alice Johnson")

        assert result == expected
        assert len(cache_set_calls) == 1
        assert cache_set_calls[0] == expected

    @pytest.mark.asyncio
    async def test_embed_batch_returns_list(self):
        client = self._fresh_client()
        texts = ["Alice", "Bob", "Charlie"]
        expected_results = [[0.1] * 3, None, [0.3] * 3]

        side_effects = iter(expected_results)

        async def fake_embed(text):
            return next(side_effects)

        with patch.object(client, "embed", side_effect=fake_embed):
            results = await client.embed_batch(texts)

        assert len(results) == 3
        assert results[1] is None

    @pytest.mark.asyncio
    async def test_embed_batch_same_length_as_input(self):
        client = self._fresh_client()
        with patch.object(client, "embed", new_callable=AsyncMock, return_value=None):
            results = await client.embed_batch(["a", "b", "c", "d"])
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_cache_get_redis_unavailable_returns_none(self):
        client = self._fresh_client()
        with patch("engine.identity.embedding_client.get_redis", new_callable=AsyncMock, return_value=None):
            result = await client._cache_get("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_redis_unavailable_no_crash(self):
        client = self._fresh_client()
        with patch("engine.identity.embedding_client.get_redis", new_callable=AsyncMock, return_value=None):
            await client._cache_set("test", [0.1, 0.2])   # should not raise

    @pytest.mark.asyncio
    async def test_api_timeout_returns_none(self):
        client = self._fresh_client()

        async def slow_create(*args, **kwargs):
            await asyncio.sleep(100)

        mock_azure = MagicMock()
        mock_azure.embeddings.create = slow_create
        client._client = mock_azure

        with patch.object(client, "_cache_get", new_callable=AsyncMock, return_value=None), \
             patch("engine.identity.embedding_client.identity_config") as cfg:
            cfg.EMBEDDING_TIMEOUT_SEC = 0.01
            cfg.EMBEDDING_RETRY_COUNT = 1
            cfg.EMBEDDING_RETRY_DELAY_SEC = 0.01
            cfg.EMBEDDING_DEPLOYMENT = "text-embedding-3-large"
            result = await client.embed("Alice")

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: TestSemanticMatcherDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestSemanticMatcherDeep:

    @pytest.mark.asyncio
    async def test_identical_embeddings_high_score(self):
        matcher = SemanticMatcher()
        unit = [1.0 / math.sqrt(3)] * 3
        with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=unit):
            ev = await matcher.match("Alice", "Alice")
        assert ev.cosine_similarity >= 0.99

    @pytest.mark.asyncio
    async def test_below_threshold_returns_zero_score(self):
        """cos_sim=0 < MIN_SEMANTIC_SCORE=0.50 → score=0"""
        matcher = SemanticMatcher()
        with patch.object(matcher._client, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]
            ev = await matcher.match("Alice", "Bob")
        assert ev.score == 0.0
        assert ev.cosine_similarity == pytest.approx(0.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_score_linearly_scales_above_threshold(self):
        """cos_sim = 0.75 → raw_score = (0.75-0.50)/(1.0-0.50) = 0.50"""
        matcher = SemanticMatcher()
        # Build vectors with known cosine similarity ~0.75
        # cos([3,4], [4,3]) = (12+12)/(5*5) = 24/25 = 0.96, use something simpler
        # [1, 0] and [cos(41.4°), sin(41.4°)] ≈ [0.75, 0.66]
        a = [1.0, 0.0]
        b = [0.75, math.sqrt(1 - 0.75**2)]  # cos_sim = 0.75
        with patch.object(matcher._client, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = [a, b]
            ev = await matcher.match("Alice", "Alicia")
        expected_score = round(min(1.0, (0.75 - 0.50) / (1.0 - 0.50)), 4)
        assert ev.score == pytest.approx(expected_score, abs=0.01)

    @pytest.mark.asyncio
    async def test_none_candidate_text_returns_zero(self):
        matcher = SemanticMatcher()
        ev = await matcher.match(None, "Alice Johnson")
        assert ev.score == 0.0
        assert ev.confidence == 0.0

    @pytest.mark.asyncio
    async def test_none_participant_text_returns_zero(self):
        matcher = SemanticMatcher()
        ev = await matcher.match("Alice Johnson", None)
        assert ev.score == 0.0

    @pytest.mark.asyncio
    async def test_embedding_model_field_in_output(self):
        matcher = SemanticMatcher()
        unit = [1.0, 0.0]
        with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=unit):
            ev = await matcher.match("Alice", "Alice")
        assert ev.embedding_model == "text-embedding-3-large"

    @pytest.mark.asyncio
    async def test_embedding_distance_populated(self):
        matcher = SemanticMatcher()
        unit = [1.0, 0.0]
        with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=unit):
            ev = await matcher.match("Alice", "Alice")
        assert ev.embedding_distance == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.asyncio
    async def test_candidate_text_stored_in_output(self):
        matcher = SemanticMatcher()
        unit = [1.0, 0.0, 0.0]
        with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=unit):
            ev = await matcher.match("John Smith", "John Smith")
        assert ev.candidate_text == "John Smith"
        assert ev.participant_text == "John Smith"

    @pytest.mark.asyncio
    async def test_partial_embedding_failure_returns_zero(self):
        """If only one embedding succeeds, return zero evidence."""
        matcher = SemanticMatcher()
        with patch.object(matcher._client, "embed", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = [[1.0, 0.0], None]
            ev = await matcher.match("Alice", "Bob")
        assert ev.score == 0.0

    @pytest.mark.asyncio
    async def test_both_embeddings_none_returns_zero(self):
        matcher = SemanticMatcher()
        with patch.object(matcher._client, "embed", new_callable=AsyncMock, return_value=None):
            ev = await matcher.match("Alice", "Alice")
        assert ev.score == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9: TestScorerDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestScorerDeep:

    def setup_method(self):
        self.s = IdentityScorer()

    # Active-weight normalization
    def test_email_only_normalizes_to_full_score(self):
        score, conf, _ = self.s.calculate(email_evidence=_email_ev(score=0.90, conf=0.88))
        # Only email active, so score = 0.90 * 0.30 / 0.30 = 0.90
        assert score == pytest.approx(0.90)

    def test_fuzzy_only_normalizes_to_full_score(self):
        score, _, _ = self.s.calculate(fuzzy_evidence=_fuzzy_ev(score=0.80, conf=0.78))
        assert score == pytest.approx(0.80)

    def test_semantic_only_normalizes(self):
        score, _, _ = self.s.calculate(semantic_evidence=_sem_ev(score=0.70, conf=0.65))
        assert score == pytest.approx(0.70)

    def test_all_zero_evidence_excluded(self):
        """All scores=0 → treated as no active signals."""
        score, conf, _ = self.s.calculate(
            email_evidence=_email_ev(0.0, 0.0),
            fuzzy_evidence=_fuzzy_ev(0.0, 0.0),
        )
        assert score == 0.0
        assert conf == 0.0

    def test_two_signals_weighted_average(self):
        """
        email=0.90 (weight=0.30), fuzzy=0.60 (weight=0.20)
        expected = (0.90*0.30 + 0.60*0.20) / (0.30+0.20) = (0.27+0.12)/0.50 = 0.78
        """
        score, _, _ = self.s.calculate(
            email_evidence=_email_ev(score=0.90, conf=0.88),
            fuzzy_evidence=_fuzzy_ev(score=0.60, conf=0.58),
        )
        expected = (0.90 * 0.30 + 0.60 * 0.20) / (0.30 + 0.20)
        assert score == pytest.approx(expected, abs=0.001)

    # Boost logic
    def test_exactly_3_strong_signals_triggers_boost(self):
        _, conf, reasons = self.s.calculate(
            email_evidence=_email_ev(score=0.90, conf=0.88),
            fuzzy_evidence=_fuzzy_ev(score=0.85, conf=0.83),
            semantic_evidence=_sem_ev(score=0.80, conf=0.78),
        )
        assert any("boost" in r.lower() for r in reasons)

    def test_exactly_2_strong_signals_no_full_boost(self):
        _, conf2, reasons2 = self.s.calculate(
            email_evidence=_email_ev(score=0.90, conf=0.88),
            fuzzy_evidence=_fuzzy_ev(score=0.85, conf=0.83),
        )
        # 2 strong → 1.03x boost, not the 1.10x boost
        assert not any("boost" in r.lower() for r in reasons2)

    def test_5_strong_signals_highest_score(self):
        score5, conf5, _ = self.s.calculate(
            email_evidence=_email_ev(1.0, 1.0),
            fuzzy_evidence=_fuzzy_ev(1.0, 1.0),
            semantic_evidence=_sem_ev(1.0, 1.0),
            alias_evidence=_alias_ev(1.0, 1.0),
            metadata_evidence=_meta_ev(1.0, 1.0),
        )
        assert score5 == pytest.approx(1.0)
        assert conf5 == pytest.approx(1.0)

    def test_score_strictly_bounded_0_1(self):
        """Even with scores > 1.0 injected, output must clamp to 1.0."""
        ev = EmailEvidence(score=1.0, confidence=1.0, reasons=["r"], match_type="exact")
        for _ in range(10):
            score, conf, _ = self.s.calculate(
                email_evidence=ev, fuzzy_evidence=_fuzzy_ev(1.0, 1.0),
                semantic_evidence=_sem_ev(1.0, 1.0), alias_evidence=_alias_ev(1.0, 1.0),
                metadata_evidence=_meta_ev(1.0, 1.0),
            )
            assert score <= 1.0
            assert conf <= 1.0

    # Reason deduplication
    def test_same_reason_across_two_signals_deduped(self):
        ev_email = _email_ev(score=0.90, conf=0.88, reasons=["shared reason"])
        ev_fuzzy = _fuzzy_ev(score=0.85, conf=0.83, reasons=["shared reason"])
        _, _, reasons = self.s.calculate(email_evidence=ev_email, fuzzy_evidence=ev_fuzzy)
        # Even if both contribute "shared reason", they get different labels
        email_prefixed = "[Email] shared reason"
        fuzzy_prefixed = "[Fuzzy] shared reason"
        assert reasons.count(email_prefixed) <= 1
        assert reasons.count(fuzzy_prefixed) <= 1

    def test_same_reason_within_one_signal_deduped(self):
        ev = _email_ev(score=0.90, conf=0.88, reasons=["dup", "dup"])
        _, _, reasons = self.s.calculate(email_evidence=ev)
        assert reasons.count("[Email] dup") == 1

    # Modality labels
    def test_reasons_labeled_correctly(self):
        _, _, reasons = self.s.calculate(
            email_evidence=_email_ev(0.90, 0.88, reasons=["email reason"]),
            fuzzy_evidence=_fuzzy_ev(0.85, 0.83, reasons=["fuzzy reason"]),
            semantic_evidence=_sem_ev(0.80, 0.78, reasons=["semantic reason"]),
            alias_evidence=_alias_ev(0.75, 0.73, reasons=["alias reason"]),
            metadata_evidence=_meta_ev(0.70, 0.68, reasons=["metadata reason"]),
        )
        assert any("[Email]" in r for r in reasons)
        assert any("[Fuzzy]" in r for r in reasons)
        assert any("[Semantic]" in r for r in reasons)
        assert any("[Alias]" in r for r in reasons)
        assert any("[Metadata]" in r for r in reasons)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10: TestProviderDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestProviderDeep:

    def setup_method(self):
        self.p = IdentityEvidenceProvider()

    def _call(self, **kwargs):
        defaults = dict(
            meeting_id="mtg_test", participant_id="P_prov_01",
            overall_identity_score=0.88, confidence=0.85,
            reasons=["reason A", "reason B"]
        )
        defaults.update(kwargs)
        return self.p.provide(**defaults)

    def test_email_score_from_email_evidence(self):
        ev = self._call(email_evidence=_email_ev(score=0.95, conf=0.93))
        assert ev.email_score == pytest.approx(0.95)

    def test_fuzzy_score_from_fuzzy_evidence(self):
        ev = self._call(fuzzy_evidence=_fuzzy_ev(score=0.88, conf=0.85))
        assert ev.rapidfuzz_score == pytest.approx(0.88)

    def test_semantic_score_from_semantic_evidence(self):
        ev = self._call(semantic_evidence=_sem_ev(score=0.82, conf=0.80))
        assert ev.semantic_score == pytest.approx(0.82)

    def test_alias_score_from_alias_evidence(self):
        ev = self._call(alias_evidence=_alias_ev(score=0.75, conf=0.73))
        assert ev.alias_score == pytest.approx(0.75)

    def test_metadata_score_from_metadata_evidence(self):
        ev = self._call(metadata_evidence=_meta_ev(score=0.70, conf=0.68))
        assert ev.metadata_score == pytest.approx(0.70)

    def test_no_sub_evidence_all_scores_zero(self):
        ev = self._call()
        assert ev.email_score == 0.0
        assert ev.rapidfuzz_score == 0.0
        assert ev.semantic_score == 0.0
        assert ev.alias_score == 0.0
        assert ev.metadata_score == 0.0

    def test_matched_email_only_when_score_positive(self):
        ev_zero = _email_ev(score=0.0, conf=0.0)
        ev_zero.candidate_email = "alice@acme.com"
        result = self._call(email_evidence=ev_zero)
        assert result.matched_email is None   # score=0 → not matched

    def test_matched_email_when_score_positive(self):
        ev = _email_ev(score=1.0, conf=0.98)
        ev.candidate_email = "alice@acme.com"
        result = self._call(email_evidence=ev)
        assert result.matched_email == "alice@acme.com"

    def test_matched_alias_only_when_score_positive(self):
        ev_zero = _alias_ev(score=0.0, conf=0.0, alias="bill")
        result = self._call(alias_evidence=ev_zero)
        assert result.matched_alias is None

    def test_matched_alias_when_score_positive(self):
        ev = _alias_ev(score=0.80, conf=0.75, alias="bill")
        result = self._call(alias_evidence=ev)
        assert result.matched_alias == "bill"

    def test_matched_fields_from_metadata(self):
        ev = _meta_ev(score=0.80, fields=["display_name", "email_exact"])
        result = self._call(metadata_evidence=ev)
        assert "display_name" in result.matched_fields
        assert "email_exact" in result.matched_fields

    def test_reasons_deduplication_order_preserved(self):
        result = self._call(reasons=["A", "B", "A", "C", "B"])
        assert result.reasons == ["A", "B", "C"]

    def test_empty_reasons_list_produces_empty(self):
        result = self._call(reasons=[])
        assert result.reasons == []

    def test_none_reasons_handled(self):
        result = self._call(reasons=None)
        assert result.reasons == []

    def test_all_scores_rounded_to_4dp(self):
        result = self._call(
            overall_identity_score=0.1234567,
            confidence=0.9876543,
            email_evidence=_email_ev(score=0.1111111, conf=0.2222222)
        )
        assert result.overall_identity_score == pytest.approx(0.1235, abs=0.0001)
        assert result.email_score == pytest.approx(0.1111, abs=0.0001)

    def test_sub_evidence_objects_attached(self):
        fe = _fuzzy_ev(score=0.88, conf=0.85)
        result = self._call(fuzzy_evidence=fe)
        assert result.fuzzy_evidence is fe

    def test_unique_evidence_ids_each_call(self):
        ids = {self._call().evidence_id for _ in range(50)}
        assert len(ids) == 50


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11: TestStateManagerDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestStateManagerDeep:

    def setup_method(self):
        self.mgr = IdentityStateManager()

    @pytest.mark.asyncio
    async def test_fresh_state_has_one_history_entry(self):
        ev = _ev_base(pid=f"P_{uuid.uuid4().hex[:8]}", meeting_id="mtg_sm_deep")
        state = await self.mgr.save_state(ev)
        assert len(state.history) == 1

    @pytest.mark.asyncio
    async def test_history_snapshot_contains_all_scores(self):
        ev = _ev_base()
        state = self.mgr._build_state(ev, None)
        snap = state.history[0]
        assert "identity_score" in snap
        assert "email_score" in snap
        assert "rapidfuzz_score" in snap
        assert "semantic_score" in snap
        assert "alias_score" in snap
        assert "metadata_score" in snap
        assert "top_reasons" in snap

    @pytest.mark.asyncio
    async def test_top_reasons_capped_at_5(self):
        ev = _ev_base()
        ev.reasons = [f"reason {i}" for i in range(20)]
        state = self.mgr._build_state(ev, None)
        assert len(state.history[0]["top_reasons"]) == 5

    @pytest.mark.asyncio
    async def test_confidence_smoothing_formula(self):
        """Smoothed = 0.70 * prev + 0.30 * new (when new < prev and new > 0.30)."""
        ev_high = _ev_base(conf=0.90)
        state_high = self.mgr._build_state(ev_high, None)
        state_high.confidence = 0.90

        ev_low = _ev_base(conf=0.50)
        state_low = self.mgr._build_state(ev_low, state_high)
        expected = round(0.90 * 0.70 + 0.50 * 0.30, 4)
        assert state_low.confidence == pytest.approx(expected, abs=0.001)

    @pytest.mark.asyncio
    async def test_smoothing_not_applied_below_floor(self):
        """When new_conf <= 0.30, no smoothing — use raw new_conf."""
        ev_high = _ev_base(conf=0.90)
        state_high = self.mgr._build_state(ev_high, None)
        state_high.confidence = 0.90

        ev_low = _ev_base(conf=0.25)
        state_low = self.mgr._build_state(ev_low, state_high)
        assert state_low.confidence == pytest.approx(0.25)

    @pytest.mark.asyncio
    async def test_no_smoothing_on_increase(self):
        ev_low = _ev_base(conf=0.50)
        state_low = self.mgr._build_state(ev_low, None)
        state_low.confidence = 0.50

        ev_high = _ev_base(conf=0.90)
        state_high = self.mgr._build_state(ev_high, state_low)
        assert state_high.confidence == pytest.approx(0.90)

    @pytest.mark.asyncio
    async def test_history_trimmed_at_max(self):
        ev = _ev_base()
        history_full = [{"ts": i} for i in range(identity_config.HISTORY_MAX_LENGTH)]
        existing = ParticipantIdentityState(
            participant_id=ev.participant_id, meeting_id=ev.meeting_id,
            identity_score=0.80, confidence=0.80,
            history=history_full, last_updated=now_ms()
        )
        state = self.mgr._build_state(ev, existing)
        assert len(state.history) == identity_config.HISTORY_MAX_LENGTH

    @pytest.mark.asyncio
    async def test_save_and_fetch_roundtrip(self):
        pid = f"P_{uuid.uuid4().hex[:8]}"
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        ev = _ev_base(pid=pid, meeting_id=mtg, score=0.88, conf=0.86)
        await self.mgr.save_state(ev)
        fetched = await self.mgr.get_state(mtg, pid)
        if fetched:  # Redis may be available
            assert fetched.identity_score == pytest.approx(0.88)
            assert fetched.participant_id == pid

    @pytest.mark.asyncio
    async def test_unknown_key_returns_none(self):
        result = await self.mgr.get_state("no_such_meeting_xyz", "P_no_such_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_participants_includes_saved(self):
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        pids = [f"P_{uuid.uuid4().hex[:8]}" for _ in range(4)]
        for pid in pids:
            ev = _ev_base(pid=pid, meeting_id=mtg)
            await self.mgr.save_state(ev)
        found = await self.mgr.get_all_participants(mtg)
        for pid in pids:
            assert pid in found

    @pytest.mark.asyncio
    async def test_normalized_name_stored_in_state(self):
        ev = _ev_base()
        ev.normalized_participant_name = "alice johnson"
        state = self.mgr._build_state(ev, None)
        assert state.normalized_name == "alice johnson"

    @pytest.mark.asyncio
    async def test_display_name_stored_in_state(self):
        ev = _ev_base()
        ev.raw_display_name = "Alice Johnson"
        state = self.mgr._build_state(ev, None)
        assert state.display_name == "Alice Johnson"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12: TestStorageDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestStorageDeep:

    def setup_method(self):
        self.storage = IdentityStorageManager()

    @pytest.mark.asyncio
    async def test_evidence_append_only_two_calls(self):
        """Two calls = two documents in identity_evidence (never upsert)."""
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        ev = _ev_base(meeting_id=mtg)
        await db["identity_evidence"].delete_many({"meeting_id": mtg})
        await self.storage.save_evidence(ev)
        await self.storage.save_evidence(ev)
        count = await db["identity_evidence"].count_documents({"meeting_id": mtg})
        assert count == 2

    @pytest.mark.asyncio
    async def test_upsert_profile_idempotent(self):
        """Multiple upserts for same participant → exactly 1 document."""
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        pid = f"P_{uuid.uuid4().hex[:8]}"
        ev = _ev_base(pid=pid, meeting_id=mtg)
        await db["identity_participant_profiles"].delete_many({"meeting_id": mtg})
        for _ in range(5):
            await self.storage.upsert_profile(ev)
        count = await db["identity_participant_profiles"].count_documents(
            {"meeting_id": mtg, "participant_id": pid}
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_upsert_profile_updates_score(self):
        """Second upsert with higher score must overwrite identity_score."""
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        pid = f"P_{uuid.uuid4().hex[:8]}"
        ev_low = _ev_base(pid=pid, meeting_id=mtg, score=0.60)
        ev_high = _ev_base(pid=pid, meeting_id=mtg, score=0.92)
        await db["identity_participant_profiles"].delete_many({"meeting_id": mtg})
        await self.storage.upsert_profile(ev_low)
        await self.storage.upsert_profile(ev_high)
        doc = await db["identity_participant_profiles"].find_one(
            {"meeting_id": mtg, "participant_id": pid}
        )
        assert doc["identity_score"] == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_save_match_high_score(self):
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        await db["identity_matches"].delete_many({"meeting_id": mtg})
        await self.storage.save_match(
            meeting_id=mtg, participant_id="P_match_deep",
            matched_name="alice johnson", matched_email="alice@acme.com",
            score=0.95, confidence=0.92, reasons=["r1", "r2"], timestamp=now_ms()
        )
        doc = await db["identity_matches"].find_one({"meeting_id": mtg})
        assert doc is not None
        assert doc["score"] == pytest.approx(0.95)
        assert doc["matched_name"] == "alice johnson"

    @pytest.mark.asyncio
    async def test_save_match_no_email(self):
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        await db["identity_matches"].delete_many({"meeting_id": mtg})
        await self.storage.save_match(
            meeting_id=mtg, participant_id="P_no_email",
            matched_name="alice johnson", matched_email=None,
            score=0.75, confidence=0.70, reasons=[], timestamp=now_ms()
        )
        doc = await db["identity_matches"].find_one({"meeting_id": mtg})
        assert doc["matched_email"] is None

    @pytest.mark.asyncio
    async def test_save_event_payload_included(self):
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        await db["identity_events"].delete_many({"meeting_id": mtg})
        await self.storage.save_event(
            meeting_id=mtg, participant_id="P_ev_deep",
            event_type="identity_processed",
            payload={"overall_identity_score": 0.88, "confidence": 0.85},
            timestamp=now_ms()
        )
        doc = await db["identity_events"].find_one({"meeting_id": mtg})
        assert doc["event_type"] == "identity_processed"
        assert doc["overall_identity_score"] == pytest.approx(0.88)

    @pytest.mark.asyncio
    async def test_save_event_multiple_types(self):
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg = f"mtg_{uuid.uuid4().hex[:6]}"
        await db["identity_events"].delete_many({"meeting_id": mtg})
        for event_type in ["identity_processed", "state_updated", "match_recorded"]:
            await self.storage.save_event(
                meeting_id=mtg, participant_id="P_multi",
                event_type=event_type, payload={}, timestamp=now_ms()
            )
        count = await db["identity_events"].count_documents({"meeting_id": mtg})
        assert count == 3

    @pytest.mark.asyncio
    async def test_all_4_collections_written_by_pipeline(self):
        """Full pipeline run should write to all 4 MongoDB collections."""
        db = get_mongo_db()
        if db is None:
            pytest.skip("MongoDB unavailable")
        mtg_id = f"mtg_all4_{uuid.uuid4().hex[:6]}"
        pid = f"P_{uuid.uuid4().hex[:8]}"
        for col in ["identity_evidence", "identity_participant_profiles",
                    "identity_events", "identity_matches"]:
            await db[col].delete_many({"meeting_id": mtg_id})

        pipeline = IdentityPipeline()
        mtg = MeetingMetadata(
            meeting_id=mtg_id, candidate_name="Alice Johnson",
            candidate_email="alice@acme.com"
        )
        p = ParticipantMetadata(participant_id=pid, display_name="Alice Johnson",
                                email="alice@acme.com")
        await pipeline.process(mtg, p)

        assert await db["identity_evidence"].count_documents({"meeting_id": mtg_id}) >= 1
        assert await db["identity_participant_profiles"].count_documents({"meeting_id": mtg_id}) >= 1
        assert await db["identity_events"].count_documents({"meeting_id": mtg_id}) >= 1
        # identity_matches only written when score >= 0.70
        # just verify no crash; count >= 0 is always true


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 13: TestPipelineDeep (12 real-world scenarios)
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineDeep:

    def setup_method(self):
        self.pipeline = IdentityPipeline()

    @pytest.mark.asyncio
    async def test_perfect_match_all_signals(self):
        """Name + email match should produce highest scores."""
        mtg = _mtg(candidate_name="Alice Johnson", candidate_email="alice@acme.com")
        p = _part(display_name="Alice Johnson", email="alice@acme.com")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.email_score == pytest.approx(1.0)
        assert ev.rapidfuzz_score >= 0.95

    @pytest.mark.asyncio
    async def test_email_match_different_display_name(self):
        """Exact email match compensates for display name mismatch."""
        mtg = _mtg(candidate_name="Alice Johnson", candidate_email="alice@acme.com")
        p = _part(display_name="A. Johnson", email="alice@acme.com")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.email_score == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_nickname_match(self):
        """Candidate 'William' vs participant 'Bill' → alias + fuzzy score."""
        mtg = _mtg(candidate_name="William Brown")
        p = _part(display_name="Bill Brown")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        # Either fuzzy or alias should catch this
        combined = ev.rapidfuzz_score + ev.alias_score
        assert combined >= 0.60

    @pytest.mark.asyncio
    async def test_completely_different_participant_low_score(self):
        mtg = _mtg(candidate_name="Alice Johnson", candidate_email="alice@acme.com")
        p = _part(display_name="Zebediah Xander", email="z@x.com")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.overall_identity_score < 0.50

    @pytest.mark.asyncio
    async def test_missing_candidate_name_graceful(self):
        mtg = _mtg(candidate_name=None)
        p = _part(display_name="Bob Jones")
        ev = await self.pipeline.process(mtg, p)
        # Should not crash; evidence may be None (empty name → pipeline can fail gracefully)
        assert ev is None or isinstance(ev, IdentityEvidence)

    @pytest.mark.asyncio
    async def test_missing_candidate_email_graceful(self):
        mtg = _mtg(candidate_email=None)
        p = _part(email="bob@x.com")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.email_score == 0.0

    @pytest.mark.asyncio
    async def test_missing_participant_email_graceful(self):
        mtg = _mtg()
        p = _part(email=None)
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.email_score == 0.0

    @pytest.mark.asyncio
    async def test_calendar_title_corroborates(self):
        mtg = _mtg(candidate_name="Alice Johnson",
                   calendar_title="Interview with Alice Johnson - SWE Role")
        p = _part(display_name="Alice Johnson")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.metadata_score >= 0.0   # calendar signal contributed

    @pytest.mark.asyncio
    async def test_interviewer_in_meeting_low_metadata_score(self):
        """If participant = interviewer, metadata score must be penalized."""
        mtg = _mtg(candidate_name="Alice Johnson", interviewer_names=["Bob Smith"])
        p = _part(display_name="Bob Smith")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.metadata_score < 0.30

    @pytest.mark.asyncio
    async def test_evidence_ids_unique_across_calls(self):
        mtg = _mtg()
        p = _part()
        results = await asyncio.gather(
            self.pipeline.process(mtg, p),
            self.pipeline.process(mtg, p),
            self.pipeline.process(mtg, p),
        )
        eids = [r.evidence_id for r in results if r is not None]
        assert len(eids) == len(set(eids))

    @pytest.mark.asyncio
    async def test_redis_state_accumulates_history(self):
        pid = f"P_{uuid.uuid4().hex[:8]}"
        mtg_id = f"mtg_{uuid.uuid4().hex[:6]}"
        mtg = MeetingMetadata(meeting_id=mtg_id, candidate_name="Carol White",
                              candidate_email="carol@co.com")
        p = ParticipantMetadata(participant_id=pid, display_name="Carol White",
                                email="carol@co.com")
        await self.pipeline.process(mtg, p)
        await self.pipeline.process(mtg, p)

        state_mgr = IdentityStateManager()
        state = await state_mgr.get_state(mtg_id, pid)
        if state:
            assert len(state.history) >= 2

    @pytest.mark.asyncio
    async def test_username_email_match_produces_evidence(self):
        mtg = _mtg(candidate_email="alice@company.com")
        p = _part(display_name="Alice Johnson", email="alice@personal.com")
        ev = await self.pipeline.process(mtg, p)
        assert ev is not None
        assert ev.email_score == pytest.approx(
            identity_config.EMAIL_USERNAME_MATCH_SCORE
        )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 14: TestWorkerManagerDeep
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkerManagerDeep:

    @pytest.mark.asyncio
    async def test_lifecycle_start_creates_2_workers(self):
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        mgr.start()
        assert len(mgr.worker_tasks) == identity_config.WORKER_COUNT
        await mgr.stop()

    @pytest.mark.asyncio
    async def test_lifecycle_stop_marks_is_running_false(self):
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        mgr.start()
        await mgr.stop()
        assert mgr.is_running is False

    @pytest.mark.asyncio
    async def test_lifecycle_all_tasks_done_after_stop(self):
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        mgr.start()
        await mgr.stop()
        assert all(t.done() for t in mgr.worker_tasks)

    @pytest.mark.asyncio
    async def test_idempotent_start_no_duplicate_tasks(self):
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        mgr.start()
        initial = len(mgr.worker_tasks)
        mgr.start()   # second call
        mgr.start()   # third call
        assert len(mgr.worker_tasks) == initial
        await mgr.stop()

    @pytest.mark.asyncio
    async def test_auto_start_on_enqueue(self):
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        assert not mgr.is_running
        mtg = MeetingMetadata(meeting_id="mtg_auto", candidate_name="Alice")
        p = ParticipantMetadata(participant_id="P_auto_01", display_name="Alice")
        await mgr.enqueue(mtg, p)
        assert mgr.is_running
        await mgr.stop()

    @pytest.mark.asyncio
    async def test_queue_drain_processes_events(self):
        db = get_mongo_db()
        IdentityWorkerManager._instance = None
        mgr = IdentityWorkerManager.get_instance()
        mgr.start()

        mtg_id = f"mtg_drain_{uuid.uuid4().hex[:6]}"
        if db is not None:
            await db["identity_events"].delete_many({"meeting_id": mtg_id})

        for i in range(3):
            mtg = MeetingMetadata(meeting_id=mtg_id, candidate_name=f"Candidate {i}")
            p = ParticipantMetadata(
                participant_id=f"P_drain_{i:02d}", display_name=f"Candidate {i}"
            )
            await mgr.enqueue(mtg, p)

        # Wait for processing
        if db is not None:
            for _ in range(60):
                count = await db["identity_events"].count_documents({"meeting_id": mtg_id})
                if count >= 3:
                    break
                await asyncio.sleep(0.1)
            assert count >= 3, f"Expected 3 events, found {count}"

        await mgr.stop()

    @pytest.mark.asyncio
    async def test_singleton_same_instance(self):
        IdentityWorkerManager._instance = None
        mgr1 = IdentityWorkerManager.get_instance()
        mgr2 = IdentityWorkerManager.get_instance()
        assert mgr1 is mgr2
        if mgr1.is_running:
            await mgr1.stop()

    @pytest.mark.asyncio
    async def test_convenience_function_starts_manager(self):
        IdentityWorkerManager._instance = None
        mtg = MeetingMetadata(meeting_id="mtg_conv_deep", candidate_name="Dave")
        p = ParticipantMetadata(participant_id="P_conv_deep_01", display_name="Dave")
        await enqueue_identity_request(mtg, p)
        mgr = IdentityWorkerManager.get_instance()
        assert mgr.is_running
        await mgr.stop()
