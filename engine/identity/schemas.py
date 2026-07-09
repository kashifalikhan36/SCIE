from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


# ──────────────────────────────────────────────────────────────────────────────
# Input Schemas
# ──────────────────────────────────────────────────────────────────────────────

class MeetingMetadata(BaseModel):
  """Meeting-level metadata sourced from the DOM extension, calendar, or recruiter.

  This is the authoritative candidate profile the Identity Engine compares against.
  """
  meeting_id: str
  candidate_name: Optional[str] = None
  candidate_email: Optional[str] = None
  candidate_phone: Optional[str] = None
  calendar_title: Optional[str] = None
  interviewer_names: List[str] = Field(default_factory=list)
  schedule_time: Optional[str] = None
  recruiter_name: Optional[str] = None
  job_title: Optional[str] = None
  extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class ParticipantMetadata(BaseModel):
  """Participant-level metadata observed from the meeting platform's participant list."""
  participant_id: str
  display_name: Optional[str] = None
  email: Optional[str] = None
  join_time: Optional[int] = None           # Epoch milliseconds
  camera_status: bool = False
  mic_status: bool = False
  platform_role: Optional[str] = None      # e.g. "host", "guest", "presenter"
  extra_metadata: Dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Sub-Evidence Schemas (one per matcher module)
# ──────────────────────────────────────────────────────────────────────────────

class EmailEvidence(BaseModel):
  """Evidence produced by EmailMatcher."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  match_type: str = "none"           # "exact" | "username" | "domain" | "none"
  candidate_email: Optional[str] = None
  participant_email: Optional[str] = None


class FuzzyEvidence(BaseModel):
  """Evidence produced by FuzzyMatcher (RapidFuzz)."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  similarity: float = 0.0
  edit_distance: int = 0
  matched_tokens: List[str] = Field(default_factory=list)
  matched_variant: Optional[str] = None   # Which name variant produced the best match


class SemanticEvidence(BaseModel):
  """Evidence produced by SemanticMatcher (Azure OpenAI embeddings)."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  cosine_similarity: float = 0.0
  embedding_distance: float = 0.0
  embedding_model: str = "text-embedding-3-large"
  candidate_text: Optional[str] = None
  participant_text: Optional[str] = None


class AliasEvidence(BaseModel):
  """Evidence produced by NicknameResolver when an alias match is found."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  matched_alias: Optional[str] = None
  canonical_name: Optional[str] = None
  alias_source: str = "nickname_dict"    # "nickname_dict" | "custom" | "computed"


class MetadataEvidence(BaseModel):
  """Evidence produced by MetadataMatcher for display name, calendar, recruiter signals."""
  score: float = Field(..., ge=0.0, le=1.0)
  confidence: float = Field(..., ge=0.0, le=1.0)
  reasons: List[str] = Field(default_factory=list)
  matched_fields: List[str] = Field(default_factory=list)   # e.g. ["display_name", "calendar_title"]


# ──────────────────────────────────────────────────────────────────────────────
# Primary Output Schema
# ──────────────────────────────────────────────────────────────────────────────

class IdentityEvidence(BaseModel):
  """Canonical output object produced by the Identity Engine.

  This is the ONLY object the Identity Engine emits.  It does NOT decide who
  the candidate is.  It provides structured, weighted evidence for the downstream
  Evidence Fusion Engine.
  """
  # Identifiers
  evidence_id: str
  meeting_id: str
  participant_id: str

  # Normalized name representations
  normalized_participant_name: Optional[str] = None
  normalized_candidate_name: Optional[str] = None

  # Raw inputs preserved for auditability
  raw_display_name: Optional[str] = None
  raw_candidate_name: Optional[str] = None
  candidate_email: Optional[str] = None
  participant_email: Optional[str] = None

  # Individual evidence scores (0.0 – 1.0)
  email_score: float = 0.0
  rapidfuzz_score: float = 0.0
  semantic_score: float = 0.0
  metadata_score: float = 0.0
  alias_score: float = 0.0

  # Aggregate identity score and confidence
  overall_identity_score: float = 0.0
  confidence: float = 0.0

  # Best-matching evidence details
  matched_alias: Optional[str] = None
  matched_email: Optional[str] = None
  matched_fields: List[str] = Field(default_factory=list)

  # Explanations
  reasons: List[str] = Field(default_factory=list)

  # Sub-evidence objects (serialized for downstream consumption)
  email_evidence: Optional[EmailEvidence] = None
  fuzzy_evidence: Optional[FuzzyEvidence] = None
  semantic_evidence: Optional[SemanticEvidence] = None
  alias_evidence: Optional[AliasEvidence] = None
  metadata_evidence: Optional[MetadataEvidence] = None

  # Timestamps
  timestamp: int


# ──────────────────────────────────────────────────────────────────────────────
# Redis State Schema
# ──────────────────────────────────────────────────────────────────────────────

class ParticipantIdentityState(BaseModel):
  """Live participant identity state cached in Azure Cache for Redis.

  Updated on every processing cycle; the history list tracks incremental
  score snapshots bounded to HISTORY_MAX_LENGTH.
  """
  participant_id: str
  meeting_id: str
  display_name: Optional[str] = None
  normalized_name: Optional[str] = None
  email: Optional[str] = None
  identity_score: float = 0.0
  semantic_score: float = 0.0
  rapidfuzz_score: float = 0.0
  email_score: float = 0.0
  alias_score: float = 0.0
  metadata_score: float = 0.0
  confidence: float = 0.0
  history: List[Dict[str, Any]] = Field(default_factory=list)
  last_updated: int
